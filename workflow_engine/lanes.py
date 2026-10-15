"""
Execution Lanes — 执行通道定义和规则化。

参考 watsonctl/agent-harness 的五级 Lane 体系。
"""

from enum import IntEnum
from dataclasses import dataclass


class Lane(IntEnum):
    """执行通道。数字越小，执行越直接。"""
    DIRECT = 0           # 直接执行：hotfix，无规划
    EXPLORE = 1          # 探索分析：结构不明确
    FULL_PIV = 2         # 完整 PIV：默认通道
    PARALLEL = 3         # 并行分片：独立子问题
    STRICT_VERIFY = 4    # 持续验证：高风险


# ── Lane 详细定义 ─────────────────────────

@dataclass
class LaneDefinition:
    lane: Lane
    name: str
    description: str
    trigger_conditions: list[str]
    workflow: list[str]
    requires_plan: bool
    requires_review: bool
    max_risk_score: int            # 此 Lane 能处理的最大风险分
    typical_duration: str           # 典型耗时


LANE_DEFINITIONS: dict[Lane, LaneDefinition] = {
    Lane.DIRECT: LaneDefinition(
        lane=Lane.DIRECT,
        name="Direct Execute",
        description="Hotfix、单文件小改、明确且低风险。",
        trigger_conditions=[
            "任务仅涉及 ≤2 个文件",
            "改动是明确的热修复",
            "风险评分 < 3",
            "不涉及 API/Schema 变更",
        ],
        workflow=["直接编辑 → 自动 lint → git commit"],
        requires_plan=False,
        requires_review=False,
        max_risk_score=3,
        typical_duration="< 5 分钟",
    ),

    Lane.EXPLORE: LaneDefinition(
        lane=Lane.EXPLORE,
        name="Explore / Map",
        description="仓库结构不明确，需要先探索才能决定怎么改。",
        trigger_conditions=[
            "Agent 首次进入此仓库",
            "用户没有提供具体文件路径",
            "任务范围模糊",
            "需要了解模块依赖关系",
        ],
        workflow=["搜索/读文件 → 输出结构地图 → 选 Lane → 执行"],
        requires_plan=False,
        requires_review=False,
        max_risk_score=5,
        typical_duration="< 10 分钟",
    ),

    Lane.FULL_PIV: LaneDefinition(
        lane=Lane.FULL_PIV,
        name="Full PIV",
        description="**默认通道。** 完整走 Plan → Implement → Validate → Review。",
        trigger_conditions=[
            "涉及多文件（>2）或多模块",
            "涉及 API/Schema 变更",
            "任务有明确的验收标准",
            "需要设计决策",
        ],
        workflow=[
            "/plan → 产出 plans/<slug>-plan.md",
            "/implement → 逐步实现 + 每步验证",
            "/validate → 全部门禁（ruff+mypy+pytest+tsc+vitest）",
            "/review → reviewer Agent 审 diff 出报告",
        ],
        requires_plan=True,
        requires_review=True,
        max_risk_score=7,
        typical_duration="30 分钟 ~ 2 小时",
    ),

    Lane.PARALLEL: LaneDefinition(
        lane=Lane.PARALLEL,
        name="Parallel Execution",
        description="任务包含多个独立子问题，可并行处理。",
        trigger_conditions=[
            "子任务之间无文件冲突",
            "每个子任务有明确的读写范围",
            "并行能实质性提升速度或质量",
            "owner 和 scope 已稳定",
        ],
        workflow=[
            "Lane Selector 拆分子任务",
            "并行分配 executor Agent（每个一个 worktree）",
            "汇合结果",
            "统一 validate → review",
        ],
        requires_plan=True,
        requires_review=True,
        max_risk_score=6,
        typical_duration="多线并行，墙钟 < 30 分钟",
    ),

    Lane.STRICT_VERIFY: LaneDefinition(
        lane=Lane.STRICT_VERIFY,
        name="Strict Verify Loop",
        description="高风险任务，必须持续验证直到全绿。",
        trigger_conditions=[
            "风险评分 ≥ 7",
            "涉及核心基础设施",
            "多依赖步骤",
            "主要风险是「假完成」",
        ],
        workflow=[
            "/plan → /implement（每步双重验证）→ /validate",
            "验证失败 → 分类 → retry/rollback → 重新验证",
            "循环直到全绿或人工介入",
        ],
        requires_plan=True,
        requires_review=True,
        max_risk_score=10,
        typical_duration="1 ~ 4 小时",
    ),
}


# ── Lane 选择规则表 ──────────────────────
# 按优先级排序，第一个匹配的规则生效

LANE_SELECTION_RULES = [
    # (条件函数引用, Lane)
    # 在 lane_selector.py 中实现具体的选择逻辑
]
