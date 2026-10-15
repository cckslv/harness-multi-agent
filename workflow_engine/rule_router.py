"""
Rule Router — 规则入口模块。

职责：
1. 接收新规则（结构化 JSON 或自然语言描述）
2. 自动判断类型（Lane / State / Gate / Contract）
3. 输出应写入的文件路径和目标分区
4. 防止规则散落或错放

这是 Harness 的"规则总入口"——所有规则通过这里进入系统。
"""

from dataclasses import dataclass, field
from typing import Optional
import datetime
import json
import os

from workflow_engine.rule_schema import (
    Rule, RuleType, RuleScope,
    classify_rule, RULE_FILE_MAP, RULE_SECTION_HEADERS
)


@dataclass
class RouteResult:
    """路由结果：规则应该写到哪里。"""
    rule: Rule
    file_path: str           # 目标文件
    section: str             # 目标分区标题
    markdown_entry: str      # 已格式化的 Markdown 条目
    json_entry: str          # JSON 版本（可被引擎直接读取）


class RuleRouter:
    """规则路由器。"""

    def __init__(self, registry_dir: str = "registry"):
        self.registry_dir = registry_dir
        self._route_log: list[RouteResult] = []

    def route(self, description: str,
              trigger: str = "",
              effect: str = "",
              source: str = "",
              scope: RuleScope = RuleScope.PROJECT,
              rule_type: Optional[RuleType] = None) -> RouteResult:
        """
        接收一条规则，自动分类并路由。

        Args:
            description: 规则描述（自然语言即可）
            trigger: 触发条件
            effect: 规则效果
            source: 来源（项目名/故事名）
            scope: 作用范围
            rule_type: 手动指定类型（可选）；不指定则自动分类

        Returns:
            RouteResult: 路由结果，含 Markdown + JSON 两种格式
        """
        # 自动分类
        if rule_type is None:
            rule_type = classify_rule(description, trigger, effect)

        # 生成 ID（基于已有规则数 + 1）
        rule_id = self._next_id(rule_type)

        # 构建规则
        rule = Rule(
            id=rule_id,
            type=rule_type,
            description=description,
            trigger=trigger,
            effect=effect,
            scope=scope,
            source=source,
        )

        # 路由到文件
        file_path = RULE_FILE_MAP[rule_type]
        section = RULE_SECTION_HEADERS[rule_type]

        # 生成 Markdown 条目
        markdown_entry = self._format_markdown(rule)
        json_entry = rule.to_json()

        result = RouteResult(
            rule=rule,
            file_path=file_path,
            section=section,
            markdown_entry=markdown_entry,
            json_entry=json_entry,
        )
        self._route_log.append(result)
        return result

    def route_from_text(self, text: str,
                        source: str = "",
                        scope: RuleScope = RuleScope.PROJECT) -> RouteResult:
        """
        从一段自由文本中提取规则。用于凡哥说"记下来：xxx"的场景。

        Args:
            text: 自然语言描述的规则
            source: 来源
            scope: 作用范围
        """
        return self.route(
            description=text,
            trigger="",
            effect="",
            source=source,
            scope=scope,
        )

    def get_log(self) -> list[RouteResult]:
        return list(self._route_log)

    def _next_id(self, rule_type: RuleType) -> str:
        """生成下一条规则 ID。"""
        prefix_map = {
            RuleType.LANE: "L",
            RuleType.STATE: "S",
            RuleType.GATE: "G",
            RuleType.CONTRACT: "C",
        }
        prefix = prefix_map[rule_type]
        # 统计同类型已有规则数
        count = sum(1 for r in self._route_log if r.rule.type == rule_type)
        return f"R-{prefix}-{count + 1:03d}"

    def _format_markdown(self, rule: Rule) -> str:
        """格式化规则为 Markdown 条目。"""
        marker_map = {
            RuleType.LANE: "[LANE]",
            RuleType.STATE: "[STATE]",
            RuleType.GATE: "[GATE]",
            RuleType.CONTRACT: "[CONTRACT]",
        }
        marker = marker_map[rule.type]

        lines = [
            f"### {marker} {rule.id} | {rule.description}",
            f"- **日期**: {rule.created[:10]}",
            f"- **类型**: {rule.type.value} ({RULE_SECTION_HEADERS[rule.type].strip('#').strip()})",
            f"- **触发**: {rule.trigger or '（无）'}",
            f"- **效果**: {rule.effect or '（无）'}",
            f"- **范围**: {rule.scope.value}",
        ]
        if rule.source:
            lines.append(f"- **来源**: {rule.source}")
        return "\n".join(lines) + "\n"


# ── 便捷函数 ──────────────────────────────

_router = RuleRouter()


def add_rule(description: str,
             trigger: str = "",
             effect: str = "",
             source: str = "",
             scope: str = "project",
             rule_type: Optional[str] = None) -> RouteResult:
    """
    便捷函数：添加一条规则。

    用法示例：
        add_rule("executor 不能修改 spec/", source="ai-agent / 登录功能")
    """
    rt = RuleType(rule_type) if rule_type else None
    sc = RuleScope(scope)
    return _router.route(description, trigger, effect, source, sc, rt)


# ── 自测 ──────────────────────────────────

if __name__ == "__main__":
    router = RuleRouter()

    # 测试 1: 自动分类
    r1 = router.route("executor 不能修改 spec 目录", source="ai-agent")
    assert r1.rule.type == RuleType.CONTRACT
    assert r1.file_path == "registry/rules.md"
    assert r1.section == "## Contract Rules"
    print(f"[PASS] Contract rule routed: {r1.rule.id} -> {r1.file_path}#{r1.section.strip('#').strip()}")
    print(r1.markdown_entry)

    # 测试 2: 自动分类 Lane
    r2 = router.route("feature 走 lane 2", "有完整需求", "执行完整 PIV", source="ai-chat")
    assert r2.rule.type == RuleType.LANE
    print(f"[PASS] Lane rule routed: {r2.rule.id}")
    print(r2.markdown_entry)

    # 测试 3: 自动分类 Gate
    r3 = router.route("lint 必须通过", "每次提交前", "拦截未格式化的代码", source="ai-chat")
    assert r3.rule.type == RuleType.GATE
    print(f"[PASS] Gate rule routed: {r3.rule.id}")

    # 测试 4: 从自由文本
    r4 = router.route_from_text("状态不能从 pending 直接跳到 done", source="ai-agent")
    assert r4.rule.type == RuleType.STATE
    print(f"[PASS] State rule from text: {r4.rule.id} -> {r4.markdown_entry.split(chr(10))[0]}")

    # 测试 5: 手动指定类型
    r5 = router.route("ci 失败走 lane 4", rule_type=RuleType.LANE, source="ai-agent")
    assert r5.rule.type == RuleType.LANE
    print(f"[PASS] Manual override: {r5.rule.id}")

    # 验证 JSON 输出
    assert '"type": "contract"' in r1.json_entry
    print(f"\n[PASS] JSON output valid")
    print(f"\n[SUMMARY] {len(router.get_log())} rules routed successfully!")
