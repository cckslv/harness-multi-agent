"""
Lane Selector — 确定性执行通道决策引擎。

核心原则：Lane 选择必须是 deterministic function，不是 prompt 行为。

输入：任务描述 + 约束 + 历史会话
输出：唯一的 Lane 0~4

可审计、可复现、可测试。
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional
import datetime

from workflow_engine.lanes import Lane, LaneDefinition, LANE_DEFINITIONS


class Scope(Enum):
    HOTFIX = "hotfix"           # 单文件紧急修复
    SINGLE_FILE = "single_file" # 单文件改动
    SINGLE_MODULE = "single_module"  # 单模块改动
    MULTI_MODULE = "multi_module"    # 跨模块
    MULTI_STORY = "multi_story"      # 跨故事
    UNKNOWN = "unknown"              # 范围不明确


@dataclass
class TaskProfile:
    """任务画像 — Lane Selector 的输入。"""
    description: str
    files_affected: list[str] = field(default_factory=list)
    modules_affected: list[str] = field(default_factory=list)
    has_api_change: bool = False
    has_schema_change: bool = False
    has_acceptance_criteria: bool = False
    is_first_session: bool = True
    has_existing_plan: bool = False
    parallelizable: bool = False
    is_critical_infra: bool = False


@dataclass
class RiskAssessment:
    """风险评估结果。"""
    score: int                     # 0-10
    factors: list[str] = field(default_factory=list)
    mitigations: list[str] = field(default_factory=list)


@dataclass
class LaneDecision:
    """Lane 选择结果。"""
    lane: Lane
    definition: LaneDefinition
    reason: str
    risk: RiskAssessment
    scope: Scope
    timestamp: str = field(default_factory=lambda: datetime.datetime.now(
        datetime.timezone.utc).isoformat())


# ── 风险评分 ─────────────────────────────

def calc_risk_score(task: TaskProfile,
                    constraints: Optional[list[str]] = None) -> RiskAssessment:
    """
    计算任务风险评分（0-10）。

    计分规则：
    - 文件数 > 5        → +2
    - 文件数 > 10       → +3
    - 跨模块            → +2
    - API 变更          → +2
    - Schema 变更       → +3
    - 首次会话（无历史） → +1
    - 关键基础设施       → +3
    - 无验收标准         → +1
    """
    score = 0
    factors = []
    mitigations = []

    n_files = len(task.files_affected)

    if n_files > 10:
        score += 3
        factors.append(f"大量文件变更 ({n_files} 个)")
        mitigations.append("确认每个文件变更的必要性")
    elif n_files > 5:
        score += 2
        factors.append(f"多文件变更 ({n_files} 个)")

    if len(task.modules_affected) > 2:
        score += 2
        factors.append(f"跨模块变更: {task.modules_affected}")

    if task.has_api_change:
        score += 2
        factors.append("涉及 API 变更")
        mitigations.append("确认 API 向后兼容")

    if task.has_schema_change:
        score += 3
        factors.append("涉及 Schema 变更")
        mitigations.append("准备数据库迁移 + 回滚脚本")

    if task.is_first_session:
        score += 1
        factors.append("首次会话，无历史上下文")

    if task.is_critical_infra:
        score += 3
        factors.append("涉及关键基础设施")
        mitigations.append("Lane 4: 持续验证循环")

    if not task.has_acceptance_criteria:
        score += 1
        factors.append("无明确验收标准")
        mitigations.append("请先补充验收标准")

    return RiskAssessment(
        score=min(score, 10),
        factors=factors,
        mitigations=mitigations,
    )


# ── 范围分类 ─────────────────────────────

def classify_scope(task: TaskProfile) -> Scope:
    """分类任务范围。"""
    n_files = len(task.files_affected)
    n_modules = len(task.modules_affected)

    if n_files == 0:
        return Scope.UNKNOWN

    if n_files <= 2 and not task.has_api_change and not task.has_schema_change:
        # 需要判断是否是 hotfix
        if "fix" in task.description.lower() or "bug" in task.description.lower():
            return Scope.HOTFIX
        return Scope.SINGLE_FILE

    if n_modules == 1:
        return Scope.SINGLE_MODULE

    if n_modules >= 2:
        return Scope.MULTI_MODULE

    if task.has_schema_change or task.has_api_change:
        return Scope.MULTI_STORY

    return Scope.MULTI_MODULE


# ── 可并行性判断 ────────────────────────

def can_parallelize(task: TaskProfile) -> bool:
    """判断任务是否可以拆分为并行子任务。"""
    if not task.parallelizable:
        return False
    # 文件数太少，并行收益不大
    if len(task.files_affected) < 3:
        return False
    # 模块间有依赖则不能并行
    if len(task.modules_affected) > 2:
        return False
    return True


# ── 主选择函数 ───────────────────────────

def select_lane(task: TaskProfile,
                constraints: Optional[list[str]] = None,
                session_history: Optional[dict] = None) -> LaneDecision:
    """
    确定性 Lane 选择函数。

    Args:
        task: 任务画像
        constraints: 项目约束列表
        session_history: 历史会话记录 {"plan_path": str|None, ...}

    Returns:
        LaneDecision: 唯一的 Lane 选择结果
    """
    risk = calc_risk_score(task, constraints)
    scope = classify_scope(task)
    session_history = session_history or {}
    has_plan = bool(session_history.get("plan_path"))

    # ── 决策树 ──────────────────────────
    # 顺序很重要，第一个匹配的规则生效

    # Rule 1: 范围未知 → 先探索
    if scope == Scope.UNKNOWN:
        lane = Lane.EXPLORE
        reason = "任务范围不明确，需要先探索仓库结构"

    # Rule 2: Hotfix + 低风险 → 直接执行
    elif scope == Scope.HOTFIX and risk.score < 3:
        lane = Lane.DIRECT
        reason = f"Hotfix，风险评分 {risk.score}/10，直接执行"

    # Rule 3: 高风险 + 关键基础设施 → 严格验证
    elif task.is_critical_infra or risk.score >= 7:
        lane = Lane.STRICT_VERIFY
        reason = f"高风险 ({risk.score}/10) 或关键基础设施，需要持续验证循环"

    # Rule 4: 可并行 → 并行执行
    elif can_parallelize(task) and scope in (Scope.MULTI_MODULE, Scope.MULTI_STORY):
        lane = Lane.PARALLEL
        reason = f"{len(task.files_affected)} 个独立文件可并行处理"

    # Rule 5: 已有方案 → 直接实施（PIV 的 I 阶段）
    elif has_plan and scope != Scope.MULTI_STORY:
        lane = Lane.FULL_PIV
        reason = "已有执行方案，进入完整 PIV 流程"

    # Rule 6: 默认 → 完整 PIV
    else:
        lane = Lane.FULL_PIV
        reason = f"默认通道：任务涉及 {len(task.files_affected)} 文件，{len(task.modules_affected)} 模块"

    definition = LANE_DEFINITIONS[lane]

    return LaneDecision(
        lane=lane,
        definition=definition,
        reason=reason,
        risk=risk,
        scope=scope,
    )


# ── 测试用例 ─────────────────────────────

if __name__ == "__main__":
    # 测试 1: Hotfix
    t1 = TaskProfile(
        description="修复登录按钮颜色 bug",
        files_affected=["app/frontend/components/login.tsx"],
        modules_affected=["frontend"],
        is_first_session=False,
    )
    d1 = select_lane(t1)
    print(f"Test 1: {d1.lane.name} → {d1.reason}")
    print(f"  Risk: {d1.risk.score}/10, Scope: {d1.scope.value}")
    assert d1.lane == Lane.DIRECT, f"Expected DIRECT, got {d1.lane}"

    # 测试 2: 未知范围
    t2 = TaskProfile(
        description="用户登录功能",
        files_affected=[],
        modules_affected=[],
        is_first_session=True,
    )
    d2 = select_lane(t2)
    print(f"Test 2: {d2.lane.name} → {d2.reason}")
    assert d2.lane == Lane.EXPLORE, f"Expected EXPLORE, got {d2.lane}"

    # 测试 3: 默认 PIV
    t3 = TaskProfile(
        description="添加 CSV 导出功能",
        files_affected=[
            "app/backend/app/routes_meetings.py",
            "app/backend/app/services/export_service.py",
            "app/backend/app/schemas/export.py",
            "app/frontend/app/meetings/page.tsx",
        ],
        modules_affected=["backend", "frontend"],
        has_api_change=True,
        has_acceptance_criteria=True,
        is_first_session=False,
    )
    d3 = select_lane(t3)
    print(f"Test 3: {d3.lane.name} → {d3.reason}")
    print(f"  Risk: {d3.risk.score}/10, Factors: {d3.risk.factors}")
    assert d3.lane == Lane.FULL_PIV, f"Expected FULL_PIV, got {d3.lane}"

    # 测试 4: 关键基础设施
    t4 = TaskProfile(
        description="修改认证中间件",
        files_affected=["app/backend/app/services/auth_jwt.py"],
        modules_affected=["backend", "auth"],
        is_critical_infra=True,
        has_api_change=True,
    )
    d4 = select_lane(t4)
    print(f"Test 4: {d4.lane.name} → {d4.reason}")
    print(f"  Risk: {d4.risk.score}/10, Mitigations: {d4.risk.mitigations}")
    assert d4.lane == Lane.STRICT_VERIFY, f"Expected STRICT_VERIFY, got {d4.lane}"

    print("\n[PASS] All lane_selector tests passed!")
