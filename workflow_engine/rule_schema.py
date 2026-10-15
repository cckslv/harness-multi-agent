"""
Rule Schema — 4 类规则的统一结构化定义。

Harness 中所有规则只分 4 类：
- Lane Policy:  影响执行路径/优先级 → lane_selector 读取
- State Machine: 影响流程/生命周期  → state_machine 读取
- Gate Policy:   影响质量标准       → gates 读取
- Contract:      影响权限/行为边界  → contract 读取
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Optional
import datetime
import json


class RuleType(Enum):
    LANE = "lane"          # 调度规则：什么时候走哪个 Lane
    STATE = "state"        # 流程规则：生命周期和状态流转
    GATE = "gate"          # 质量规则：通过标准
    CONTRACT = "contract"  # 权限规则：Agent 行为边界


class RuleScope(Enum):
    GLOBAL = "global"    # 全局生效，所有项目
    PROJECT = "project"  # 仅当前项目


# ── 分类判断逻辑 ──────────────────────────
# 关键词 → RuleType 映射表

CLASSIFICATION_KEYWORDS: dict[RuleType, list[str]] = {
    RuleType.LANE: [
        "lane", "执行通道", "hotfix", "feature", "路径",
        "优先级", "调度", "并行", "验证循环",
        "什么时候", "哪个 lane", "走哪个",
    ],
    RuleType.STATE: [
        "状态", "流转", "生命周期", "阶段", "phase",
        "pending", "running", "review", "done", "retry",
        "跳转", "回退", "pipeline",
    ],
    RuleType.GATE: [
        "门禁", "检查", "校验", "通过", "test", "lint",
        "coverage", "覆盖率", "质量标准", "pass",
        "build", "type check", "mypy", "ruff",
    ],
    RuleType.CONTRACT: [
        "权限", "不能", "禁止", "允许", "只读",
        "边界", "范围", "越权", "planner", "executor",
        "reviewer", "verifier", "spec", "app",
    ],
}


# ── 规则数据结构 ──────────────────────────

@dataclass
class Rule:
    id: str                          # R-001, R-002...
    type: RuleType
    description: str                 # 一句话描述
    trigger: str                     # 触发条件（什么时候应用）
    effect: str                      # 规则效果（应用后会发生什么）
    scope: RuleScope = RuleScope.PROJECT
    source: str = ""                 # 来源：哪个项目/哪次失误
    created: str = field(default_factory=lambda: datetime.datetime.now(
        datetime.timezone.utc).isoformat())
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.type.value,
            "description": self.description,
            "trigger": self.trigger,
            "effect": self.effect,
            "scope": self.scope.value,
            "source": self.source,
            "created": self.created,
            "metadata": self.metadata,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, indent=2)

    @classmethod
    def from_dict(cls, d: dict) -> "Rule":
        return cls(
            id=d["id"],
            type=RuleType(d["type"]),
            description=d["description"],
            trigger=d.get("trigger", ""),
            effect=d.get("effect", ""),
            scope=RuleScope(d.get("scope", "project")),
            source=d.get("source", ""),
            created=d.get("created", ""),
            metadata=d.get("metadata", {}),
        )


# ── 分类器 ────────────────────────────────

def classify_rule(description: str, trigger: str = "",
                  effect: str = "") -> RuleType:
    """
    根据规则文本自动判断规则类型。

    判断逻辑（优先级从高到低）：
    1. 影响执行路径/优先级 → Lane Policy
    2. 影响流程/生命周期 → State Machine
    3. 影响质量标准 → Gate Policy
    4. 影响权限/行为边界 → Contract
    """
    text = (description + " " + trigger + " " + effect).lower()

    scores: dict[RuleType, int] = {rt: 0 for rt in RuleType}

    for rule_type, keywords in CLASSIFICATION_KEYWORDS.items():
        for kw in keywords:
            if kw.lower() in text:
                scores[rule_type] += 1

    # 得分最高的类型
    best_type = max(scores, key=scores.get)

    # 如果最高分为 0（无关键词匹配），默认 contract（最安全：先限制再放开）
    if scores[best_type] == 0:
        return RuleType.CONTRACT

    return best_type


# ── 路由表 ────────────────────────────────

RULE_FILE_MAP: dict[RuleType, str] = {
    RuleType.LANE:     "registry/rules.md",       # Lane + State 存在 rules.md
    RuleType.STATE:    "registry/rules.md",
    RuleType.GATE:     "registry/rules.md",
    RuleType.CONTRACT: "registry/rules.md",       # 也存 rules.md，但 contract.py 专门读取
}

# Rules.md 中的分区标记
RULE_SECTION_HEADERS: dict[RuleType, str] = {
    RuleType.LANE:     "## Lane Policy Rules",
    RuleType.STATE:    "## State Machine Rules",
    RuleType.GATE:     "## Gate Policy Rules",
    RuleType.CONTRACT: "## Contract Rules",
}


# ── 自测 ──────────────────────────────────

if __name__ == "__main__":
    # 测试分类
    assert classify_rule("feature 走 lane 2 执行", "", "") == RuleType.LANE
    assert classify_rule("hotfix 直接执行 lane 0", "", "") == RuleType.LANE
    assert classify_rule("状态流转 pending 到 running", "", "") == RuleType.STATE
    assert classify_rule("lint 必须 pass 才能通过", "", "") == RuleType.GATE
    assert classify_rule("executor 不能修改 spec 文件", "", "") == RuleType.CONTRACT
    assert classify_rule("reviewer 只读 diff", "", "") == RuleType.CONTRACT

    print("[PASS] Rule classification tests passed!")

    # 测试结构化
    r = Rule(
        id="R-001",
        type=RuleType.CONTRACT,
        description="executor 不能修改 spec/ 目录",
        trigger="任何 executor 角色的 Write/Edit 操作",
        effect="PreToolUse hook 拦截 executor 对 spec/* 的写入",
        scope=RuleScope.GLOBAL,
        source="ai-agent / 首次集成测试",
    )
    print(f"\n[PASS] Rule schema test:")
    print(r.to_json())
