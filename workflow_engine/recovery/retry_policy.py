"""
重试策略 — 指数退避、最大重试、升级逻辑。
"""

from dataclasses import dataclass, field
from enum import Enum
import time
import random
from typing import Optional

from workflow_engine.recovery.failure_classifier import (
    FailureReport, RecoveryAction, FailureType
)


class RetryDecision(Enum):
    RETRY = "retry"
    ESCALATE = "escalate"
    ABORT = "abort"


@dataclass
class RetryPolicy:
    """重试策略配置。"""
    max_retries: int = 3
    backoff_base: float = 2.0       # 指数退避基数（秒）
    max_backoff: float = 60.0       # 最大退避时间（秒）
    jitter: bool = True             # 是否加随机抖动
    escalate_after: int = 2         # 连续失败 > 此次数 → 升级到人工

    # 哪些失败类型可以自动修复
    auto_fix_types: tuple = (FailureType.LINT_FAIL,)


@dataclass
class RetryState:
    """当前重试状态。"""
    story_id: str
    attempts: int = 0
    last_error: Optional[FailureReport] = None
    next_retry_at: float = 0.0      # Unix timestamp
    consecutive_failures: int = 0


class RetryManager:
    """重试管理器。"""

    def __init__(self, policy: RetryPolicy = None):
        self.policy = policy or RetryPolicy()
        self._states: dict[str, RetryState] = {}

    def get_state(self, story_id: str) -> RetryState:
        """获取或创建故事的重试状态。"""
        if story_id not in self._states:
            self._states[story_id] = RetryState(story_id=story_id)
        return self._states[story_id]

    def decide(self, story_id: str,
               failure: Optional[FailureReport] = None) -> RetryDecision:
        """决定下一步：重试 / 升级 / 放弃。"""
        state = self.get_state(story_id)

        if failure:
            state.attempts += 1
            state.last_error = failure
            state.consecutive_failures += 1
        else:
            # 成功时重置连续失败计数
            state.consecutive_failures = 0
            return RetryDecision.RETRY

        # 超过最大重试次数
        if state.attempts > self.policy.max_retries:
            return RetryDecision.ABORT

        # 连续失败超过升级阈值
        if state.consecutive_failures > self.policy.escalate_after:
            return RetryDecision.ESCALATE

        # 计算退避时间
        if failure.action in (RecoveryAction.BACKOFF_RETRY, RecoveryAction.RETRY):
            backoff = self._calc_backoff(state.consecutive_failures)
            state.next_retry_at = time.time() + backoff

        return RetryDecision.RETRY

    def wait_if_needed(self, story_id: str) -> None:
        """如果需要等待退避，阻塞到退避时间。"""
        state = self.get_state(story_id)
        now = time.time()
        if state.next_retry_at > now:
            sleep_time = state.next_retry_at - now
            time.sleep(sleep_time)

    def reset(self, story_id: str) -> None:
        """重置重试状态（故事完成后）。"""
        self._states.pop(story_id, None)

    def can_auto_fix(self, failure: FailureReport) -> bool:
        """检查失败类型是否可自动修复。"""
        return failure.failure_type in self.policy.auto_fix_types

    def _calc_backoff(self, consecutive: int) -> float:
        """计算退避时间 = base^consecutive + jitter。"""
        base = self.policy.backoff_base ** consecutive
        backoff = min(base, self.policy.max_backoff)
        if self.policy.jitter:
            backoff += random.uniform(0, backoff * 0.1)
        return backoff


# ── 自测 ──────────────────────────────────

if __name__ == "__main__":
    from workflow_engine.recovery.failure_classifier import FailureClassifier

    fc = FailureClassifier()
    rm = RetryManager()

    story_id = "test-story"

    # 第一次失败 → retry
    f1 = fc.classify("ruff", "E501 line too long")
    d1 = rm.decide(story_id, f1)
    assert d1 == RetryDecision.RETRY
    print(f"[PASS] Attempt 1 → {d1.value}")

    # 第二次 → retry
    f2 = fc.classify("ruff", "F401 imported but unused")
    d2 = rm.decide(story_id, f2)
    assert d2 == RetryDecision.RETRY
    print(f"[PASS] Attempt 2 → {d2.value}")

    # 第三次 → escalate (超过 escalate_after=2)
    f3 = fc.classify("ruff", "W293 blank line contains whitespace")
    d3 = rm.decide(story_id, f3)
    assert d3 == RetryDecision.ESCALATE
    print(f"[PASS] Attempt 3 (consecutive={rm.get_state(story_id).consecutive_failures}) → {d3.value}")

    # 再失败 → abort (超过 max_retries=3)
    f4 = fc.classify("pytest", "test failed")
    d4 = rm.decide(story_id, f4)
    print(f"[PASS] Attempt 4 → {d4.value} (max_retries exceeded)")

    # auto-fix 检查
    assert rm.can_auto_fix(f1) == True
    assert rm.can_auto_fix(f4) == False

    print(f"\n[PASS] All retry_policy tests passed!")
