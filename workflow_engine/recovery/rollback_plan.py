"""
回滚方案 — 根据失败阶段确定回滚策略。

回滚策略：
- planning 阶段失败 → 重写方案，不回滚代码
- implementing 阶段失败 → 回退代码到 pre-implement 状态
- validating 阶段失败 → 保留代码，回到 implementing
- reviewing 阶段被拒 → 回退到 planning
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Optional
import datetime


class RollbackScope(Enum):
    NONE = "none"              # 无需回滚
    FILE_CHANGES = "file_changes"  # 回退文件变更
    PLAN = "plan"              # 废弃方案
    STORY = "story"            # 回到故事起点


@dataclass
class RollbackPlan:
    story_id: str
    session_id: str
    from_phase: str              # 当前失败的阶段
    scope: RollbackScope
    actions: list[str] = field(default_factory=list)
    git_ref_before: str = ""     # 变更前的 git ref
    files_to_revert: list[str] = field(default_factory=list)
    timestamp: str = field(default_factory=lambda: datetime.datetime.now(
        datetime.timezone.utc).isoformat())


# ── 阶段 → 回滚范围映射 ──────────────────

PHASE_ROLLBACK_MAP: dict[str, RollbackScope] = {
    "planning":     RollbackScope.PLAN,          # 方案有问题，废弃重写
    "planning_failed": RollbackScope.NONE,       # 方案写不出来，无代码变更
    "implementing": RollbackScope.FILE_CHANGES,  # 代码有问题，回退文件
    "implementing_failed": RollbackScope.FILE_CHANGES,
    "validating":   RollbackScope.FILE_CHANGES,  # 验证不过，修复代码
    "validating_failed": RollbackScope.FILE_CHANGES,
    "reviewing":    RollbackScope.PLAN,          # 审阅驳回，回退方案
    "reviewing_rejected": RollbackScope.PLAN,
    "done":         RollbackScope.NONE,          # 已完成，无需回滚
}


class RollbackExecutor:
    """回滚执行器。"""

    def __init__(self, event_emitter=None):
        self._events = event_emitter
        self._history: list[RollbackPlan] = []

    def plan_rollback(self, story_id: str, session_id: str,
                      from_phase: str,
                      files_changed: list[str] = None,
                      git_ref: str = "") -> RollbackPlan:
        """根据当前阶段生成回滚方案。"""
        scope = PHASE_ROLLBACK_MAP.get(from_phase, RollbackScope.NONE)

        actions = self._generate_actions(from_phase, scope, files_changed or [])

        plan = RollbackPlan(
            story_id=story_id,
            session_id=session_id,
            from_phase=from_phase,
            scope=scope,
            actions=actions,
            git_ref_before=git_ref,
            files_to_revert=files_changed or [],
        )
        self._history.append(plan)

        if self._events:
            self._events.emit("rollback_planned", plan.__dict__)

        return plan

    def _generate_actions(self, phase: str, scope: RollbackScope,
                          files: list[str]) -> list[str]:
        """生成具体的回滚操作列表。"""
        actions = []

        if scope == RollbackScope.NONE:
            actions.append("[OK] 无需回滚，继续下一阶段")
            return actions

        if scope == RollbackScope.PLAN:
            actions.append("[PLAN] 废弃当前方案，回到 planning 阶段")
            actions.append("   1. 标记 plan 文件为 deprecated")
            actions.append("   2. 重新分析需求")
            actions.append("   3. 产出新方案")
            return actions

        if scope == RollbackScope.FILE_CHANGES:
            if files:
                actions.append(f"[REVERT] 回退 {len(files)} 个文件:")
                for f in files:
                    actions.append(f"   git checkout -- {f}")
            else:
                actions.append("[REVERT] 回退所有变更:")
                actions.append("   git checkout -- .")
            actions.append(f"   当前阶段: {phase}")
            actions.append("   回到 implementing 阶段重新修改")
            return actions

        if scope == RollbackScope.STORY:
            actions.append("[BACK] 回到故事起点:")
            actions.append("   1. 回退所有文件变更")
            actions.append("   2. 废弃方案")
            actions.append("   3. 故事状态 → pending")
            return actions

        return actions

    def get_history(self, story_id: str = None) -> list[RollbackPlan]:
        if story_id:
            return [p for p in self._history if p.story_id == story_id]
        return list(self._history)


# ── 自测 ──────────────────────────────────

if __name__ == "__main__":
    executor = RollbackExecutor()

    # implementing 阶段失败
    p1 = executor.plan_rollback(
        "s1", "sess-1", "implementing",
        files_changed=["app/backend/routes.py", "app/backend/service.py"],
        git_ref="abc123"
    )
    assert p1.scope == RollbackScope.FILE_CHANGES
    assert len(p1.actions) > 0
    print(f"[PASS] Implementing fail → {p1.scope.value}")
    for action in p1.actions:
        print(f"  {action}")

    # reviewing 被拒
    p2 = executor.plan_rollback("s2", "sess-1", "reviewing_rejected")
    assert p2.scope == RollbackScope.PLAN
    print(f"[PASS] Review rejected → {p2.scope.value}")
    for action in p2.actions:
        print(f"  {action}")

    # done — 无需回滚
    p3 = executor.plan_rollback("s3", "sess-1", "done")
    assert p3.scope == RollbackScope.NONE
    print(f"[PASS] Done → {p3.scope.value}")

    print(f"\n[PASS] All rollback_plan tests passed!")
