"""
权限隔离 — 角色级别的 Tool/FileSystem/MCP 权限控制。

不是 Prompt 约束，是 tool-level enforce。
配合 PreToolUse Hook 使用：每次工具调用前检查权限矩阵。
"""

from enum import Enum
from typing import Optional
import fnmatch
import json


class AgentRole(Enum):
    PLANNER = "planner"
    EXECUTOR = "executor"
    REVIEWER = "reviewer"
    VERIFIER = "verifier"


class Action(Enum):
    READ = "read"
    WRITE = "write"
    EXECUTE = "execute"


class Decision(Enum):
    ALLOW = "allow"
    DENY = "deny"


# ── 角色权限矩阵 ──────────────────────────
# 格式：{ role: { action: [path_patterns] } }
# deny 优先级高于 allow
# "*" = 匹配所有

ROLE_PERMISSIONS: dict[AgentRole, dict] = {
    AgentRole.PLANNER: {
        "read_files":    ["*"],
        "write_files":   ["plans/*", "spec/*", "reports/*"],
        "deny_files":    ["*.py", "*.ts", "*.tsx", "*.sql", "*.js", "*.jsx",
                          "*.json", "*.toml", "*.yaml", "*.yml", "*.lock",
                          "Dockerfile", "Makefile", "*.sh"],
        "deny_commands": ["rm *", "git push *", "git commit *", "docker *",
                          "npm publish *", "pip install *"],
        "mcp_allow":     ["postgres", "github"],
        "mcp_deny":      [],
    },

    AgentRole.EXECUTOR: {
        "read_files":    ["*"],
        "write_files":   ["app/**", "tests/**", "gates/**", "persistence/**"],
        "deny_files":    ["spec/*", "plans/*", ".claude/*",
                          "ARCHITECTURE.md", "AGENTS.md"],
        "deny_commands": ["rm -rf *", "git push --force *", "docker rm *"],
        "mcp_allow":     ["postgres", "codebase-search"],
        "mcp_deny":      ["github"],
    },

    AgentRole.REVIEWER: {
        "read_files":    ["*"],
        "write_files":   [],
        "deny_files":    ["*"],
        "deny_commands": ["*"],
        "mcp_allow":     ["codebase-search", "github"],
        "mcp_deny":      ["postgres"],
    },

    AgentRole.VERIFIER: {
        "read_files":    ["*"],
        "write_files":   ["reports/*"],
        "deny_files":    ["app/**", "spec/*", "plans/*", "persistence/**"],
        "deny_commands": ["rm *", "git *", "docker *"],
        "mcp_allow":     ["postgres", "playwright"],
        "mcp_deny":      ["github", "codebase-search"],
    },
}

# ── MCP 工具操作映射 ──────────────────────
# 哪些 MCP tool 算 "write" 操作

MCP_WRITE_TOOLS = {
    "github": [
        "create_pull_request", "create_issue", "create_branch",
        "push_files", "merge_pull_request", "update_file",
        "create_or_update_file", "delete_file",
    ],
    "postgres": [
        "execute_write",  # INSERT / UPDATE / DELETE / DROP
    ],
    "playwright": [
        "browser_click", "browser_type", "browser_fill_form",
        "browser_select_option", "browser_drag",
        "browser_press_key", "browser_file_upload",
    ],
}


class ContractViolation(Exception):
    """权限契约违反异常。"""
    def __init__(self, role: str, action: str, target: str, reason: str):
        self.role = role
        self.action = action
        self.target = target
        self.reason = reason
        super().__init__(
            f"[CONTRACT VIOLATION] {role} attempted {action} on {target}: {reason}"
        )


class Contract:
    """角色权限契约引擎。"""

    def __init__(self, role: AgentRole):
        self.role = role
        self.perms = ROLE_PERMISSIONS[role]
        self._violations: list[dict] = []

    # ── 文件系统权限检查 ────────────────

    def can_read_file(self, file_path: str) -> Decision:
        """检查是否可以读取文件。读权限走白名单，不受 deny_files 限制。"""
        return self._check_allow_only("read_files", file_path)

    def can_write_file(self, file_path: str) -> Decision:
        """检查是否可以写入文件。"""
        deny = self._match_any(file_path, self.perms.get("deny_files", []))
        if deny:
            return Decision.DENY
        # 没有 write_files 权限 → 拒绝（白名单模式）
        if not self._match_any(file_path, self.perms.get("write_files", [])):
            return Decision.DENY
        return Decision.ALLOW

    # ── 命令权限检查 ──────────────────

    def can_execute_command(self, command: str) -> Decision:
        """检查是否可以执行 shell 命令。"""
        denials = self.perms.get("deny_commands", [])
        for pattern in denials:
            # 支持通配符匹配命令
            if pattern == "*":
                return Decision.DENY
            if pattern.endswith("*"):
                if command.strip().startswith(pattern[:-1].rstrip()):
                    return Decision.DENY
            elif fnmatch.fnmatch(command.strip(), pattern):
                return Decision.DENY
        return Decision.ALLOW

    # ── MCP 权限检查 ──────────────────

    def can_use_mcp(self, mcp_server: str, tool_name: Optional[str] = None) -> Decision:
        """检查是否可以使用 MCP 工具。"""
        # 先检查 deny
        for deny_pat in self.perms.get("mcp_deny", []):
            if fnmatch.fnmatch(mcp_server, deny_pat):
                return Decision.DENY

        # 再检查 allow
        for allow_pat in self.perms.get("mcp_allow", []):
            if fnmatch.fnmatch(mcp_server, allow_pat):
                # 进一步检查：tool 是否是 write 操作
                if tool_name and self._is_mcp_write(mcp_server, tool_name):
                    # write 操作需要额外判断：reviewer/verifier 不允许 mcp write
                    if self.role in (AgentRole.REVIEWER, AgentRole.VERIFIER):
                        return Decision.DENY
                return Decision.ALLOW

        return Decision.DENY

    # ── 综合检查 ──────────────────────

    def check_file_access(self, file_path: str, action: Action) -> Decision:
        if action == Action.READ:
            return self.can_read_file(file_path)
        return self.can_write_file(file_path)

    def raise_if_denied(self, action: str, target: str,
                        decision: Decision, reason: str = "") -> None:
        """如果权限拒绝，直接抛出 ContractViolation。"""
        if decision == Decision.DENY:
            violation = {
                "role": self.role.value,
                "action": action,
                "target": target,
                "reason": reason or f"{action} not allowed for {self.role.value}",
                "timestamp": __import__('datetime').datetime.now(
                    __import__('datetime').timezone.utc
                ).isoformat(),
            }
            self._violations.append(violation)
            raise ContractViolation(
                self.role.value, action, target,
                reason or f"Access denied by contract"
            )

    def get_violations(self) -> list[dict]:
        return list(self._violations)

    # ── 私有方法 ──────────────────────

    def _check_allow_only(self, allow_key: str, file_path: str) -> Decision:
        """纯白名单检查，不经过 deny_files。用于读权限。"""
        for allow_pat in self.perms.get(allow_key, []):
            if fnmatch.fnmatch(file_path, allow_pat):
                return Decision.ALLOW
        return Decision.DENY

    def _check_files(self, allow_key: str, file_path: str) -> Decision:
        """通用文件权限检查。"""
        # deny 优先
        for deny_pat in self.perms.get("deny_files", []):
            if fnmatch.fnmatch(file_path, deny_pat):
                return Decision.DENY
        # allow 检查
        for allow_pat in self.perms.get(allow_key, []):
            if fnmatch.fnmatch(file_path, allow_pat):
                return Decision.ALLOW
        # 默认拒绝（白名单模式）
        return Decision.DENY

    def _match_any(self, target: str, patterns: list[str]) -> bool:
        for pat in patterns:
            if fnmatch.fnmatch(target, pat):
                return True
        return False

    def _is_mcp_write(self, server: str, tool: str) -> bool:
        write_tools = MCP_WRITE_TOOLS.get(server, [])
        return tool in write_tools or tool.startswith("create_") or tool.startswith("delete_") or tool.startswith("update_")


# ── Hook 集成接口 ────────────────────────

def hook_check(role_str: str, tool_name: str, tool_input: dict) -> dict:
    """
    供 PreToolUse Hook 调用的入口函数。

    Args:
        role_str: "planner" | "executor" | "reviewer" | "verifier"
        tool_name: 工具名，如 "Write", "Bash", "mcp__github__create_pr"
        tool_input: 工具输入参数

    Returns:
        {"decision": "allow"} 或 {"decision": "deny", "reason": "..."}
    """
    role = AgentRole(role_str)
    contract = Contract(role)

    try:
        if tool_name in ("Read", "Glob", "Grep", "LSP"):
            file_path = tool_input.get("file_path", "")
            if contract.can_read_file(file_path) == Decision.DENY:
                return {"decision": "deny",
                        "reason": f"{role_str} cannot read {file_path}"}

        elif tool_name in ("Write", "Edit"):
            file_path = tool_input.get("file_path", "")
            if contract.can_write_file(file_path) == Decision.DENY:
                return {"decision": "deny",
                        "reason": f"{role_str} cannot write to {file_path}"}

        elif tool_name == "Bash":
            command = tool_input.get("command", "")
            if contract.can_execute_command(command) == Decision.DENY:
                return {"decision": "deny",
                        "reason": f"{role_str} cannot execute: {command}"}

        elif tool_name.startswith("mcp__"):
            # mcp__server__tool → server="server", tool="tool"
            parts = tool_name.split("__")
            if len(parts) >= 2:
                server = parts[1]
                mcp_tool = parts[2] if len(parts) > 2 else None
                if contract.can_use_mcp(server, mcp_tool) == Decision.DENY:
                    return {"decision": "deny",
                            "reason": f"{role_str} cannot use MCP {server}/{mcp_tool}"}

    except Exception as e:
        # 异常时放行（failsafe: 不让权限检查卡死会话）
        return {"decision": "allow", "warning": str(e)}

    return {"decision": "allow"}
