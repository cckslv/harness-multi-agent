"""
失败分类器 — 将执行失败映射到标准类型，触发对应的恢复策略。
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Optional
import datetime


class FailureType(Enum):
    LINT_FAIL = "lint_fail"              # 代码风格 / lint 不通过
    TEST_FAIL = "test_fail"              # 单元测试 / 集成测试失败
    TYPE_CHECK_FAIL = "type_check_fail"  # 类型检查失败
    BUILD_FAIL = "build_fail"            # 编译 / 构建失败
    GATE_FAIL = "gate_fail"              # 门禁综合失败（多检查中至少一项失败）
    DESIGN_MISMATCH = "design_mismatch"  # 实现偏离设计方案
    CI_FAIL = "ci_fail"                  # CI 流水线失败
    TIMEOUT = "timeout"                  # 执行超时
    UNKNOWN = "unknown"                  # 无法分类


class RecoveryAction(Enum):
    AUTO_FIX = "auto_fix"          # 自动修复（如 lint fix）
    RETRY = "retry"                # 重试当前步骤
    BACKOFF_RETRY = "backoff_retry"  # 退避重试
    ROLLBACK = "rollback"          # 回退到上一阶段
    ESCALATE = "escalate"          # 升级到人工介入
    FREEZE = "freeze"              # 冻结，等待人工决策
    ABORT = "abort"                # 放弃当前故事


@dataclass
class FailureReport:
    failure_type: FailureType
    action: RecoveryAction
    story_id: str
    session_id: str
    gate_name: str = ""            # 哪个门禁失败
    error_message: str = ""
    context: dict = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.datetime.now(
        datetime.timezone.utc).isoformat())


# ── 失败类型 → 恢复动作映射 ──────────────

FAILURE_ACTION_MAP: dict[FailureType, RecoveryAction] = {
    FailureType.LINT_FAIL:        RecoveryAction.AUTO_FIX,
    FailureType.TEST_FAIL:        RecoveryAction.RETRY,
    FailureType.TYPE_CHECK_FAIL:  RecoveryAction.RETRY,
    FailureType.BUILD_FAIL:       RecoveryAction.RETRY,
    FailureType.GATE_FAIL:        RecoveryAction.BACKOFF_RETRY,
    FailureType.DESIGN_MISMATCH:  RecoveryAction.ROLLBACK,
    FailureType.CI_FAIL:          RecoveryAction.FREEZE,
    FailureType.TIMEOUT:          RecoveryAction.ESCALATE,
    FailureType.UNKNOWN:          RecoveryAction.ESCALATE,
}

# ── 每个动作的最大重试次数 ────────────────

ACTION_MAX_RETRIES: dict[RecoveryAction, int] = {
    RecoveryAction.AUTO_FIX:       3,
    RecoveryAction.RETRY:          3,
    RecoveryAction.BACKOFF_RETRY:  2,
    RecoveryAction.ROLLBACK:       1,
    RecoveryAction.ESCALATE:       0,   # 不重试，直接升级
    RecoveryAction.FREEZE:         0,
    RecoveryAction.ABORT:          0,
}


class FailureClassifier:
    """失败分类器引擎。"""

    def __init__(self, event_emitter=None):
        self._events = event_emitter
        self._failure_log: list[FailureReport] = []

    def classify(self, gate_name: str, error_message: str,
                 story_id: str = "", session_id: str = "",
                 context: dict = None) -> FailureReport:
        """根据 gate_name + error_message 联合分类。"""
        search_text = (gate_name + ' ' + error_message).lower()

        # 关键词匹配分类
        if any(kw in search_text for kw in ('lint', 'ruff', 'eslint', 'format')):
            ftype = FailureType.LINT_FAIL
        elif any(kw in search_text for kw in ('test', 'assert', 'pytest', 'vitest', 'fail')):
            ftype = FailureType.TEST_FAIL
        elif any(kw in search_text for kw in ('type', 'mypy', 'tsc', 'typecheck')):
            ftype = FailureType.TYPE_CHECK_FAIL
        elif any(kw in search_text for kw in ('build', 'compile', 'tsc', 'vite')):
            ftype = FailureType.BUILD_FAIL
        elif any(kw in search_text for kw in ('design', 'mismatch', 'spec')):
            ftype = FailureType.DESIGN_MISMATCH
        elif any(kw in search_text for kw in ('timeout', 'timed out', 'deadline')):
            ftype = FailureType.TIMEOUT
        elif any(kw in search_text for kw in ('ci', 'pipeline', 'github actions')):
            ftype = FailureType.CI_FAIL
        else:
            ftype = FailureType.UNKNOWN

        action = FAILURE_ACTION_MAP[ftype]

        report = FailureReport(
            failure_type=ftype,
            action=action,
            story_id=story_id,
            session_id=session_id,
            gate_name=gate_name,
            error_message=error_message,
            context=context or {},
        )
        self._failure_log.append(report)

        # 发射事件
        if self._events:
            self._events.emit("failure_classified", report.__dict__)

        return report

    def can_retry(self, report: FailureReport, attempts: int) -> bool:
        """检查是否还能重试。"""
        max_retries = ACTION_MAX_RETRIES.get(report.action, 0)
        return attempts < max_retries

    def get_failures(self, story_id: str = None) -> list[FailureReport]:
        """获取失败记录，可按故事过滤。"""
        if story_id:
            return [f for f in self._failure_log if f.story_id == story_id]
        return list(self._failure_log)


# ── 自测 ──────────────────────────────────

if __name__ == "__main__":
    fc = FailureClassifier()

    # lint fail
    r1 = fc.classify("ruff", "E501 line too long (89 > 88 characters)")
    assert r1.failure_type == FailureType.LINT_FAIL
    assert r1.action == RecoveryAction.AUTO_FIX
    print(f"[PASS] Lint fail → {r1.action.value}")

    # test fail
    r2 = fc.classify("pytest", "AssertionError: expected 200, got 500")
    assert r2.failure_type == FailureType.TEST_FAIL
    assert r2.action == RecoveryAction.RETRY
    print(f"[PASS] Test fail → {r2.action.value}")

    # design mismatch
    r3 = fc.classify("review", "Implementation does not match the design spec")
    assert r3.failure_type == FailureType.DESIGN_MISMATCH
    assert r3.action == RecoveryAction.ROLLBACK
    print(f"[PASS] Design mismatch → {r3.action.value}")

    # timeout
    r4 = fc.classify("executor", "Task timed out after 600s")
    assert r4.failure_type == FailureType.TIMEOUT
    assert r4.action == RecoveryAction.ESCALATE
    print(f"[PASS] Timeout → {r4.action.value}")

    # retry check
    assert fc.can_retry(r2, 0) == True
    assert fc.can_retry(r2, 3) == False  # max 3 retries, 0-indexed
    print(f"[PASS] Retry policy: 3 attempts, exceeded at 4th")

    print(f"\n[PASS] All failure_classifier tests passed!")
