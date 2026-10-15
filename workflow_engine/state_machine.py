"""
状态机约束 — Agent 运行状态流转的唯一入口。

所有 story/session 状态更新必须通过 transition() 函数，
禁止直接写 DB 或修改 status 字段。
"""

from enum import Enum
from typing import Optional, Set
import datetime


class StoryStatus(Enum):
    PENDING = "pending"
    PLANNING = "planning"
    PLANNED = "planned"
    IMPLEMENTING = "implementing"
    IMPLEMENTED = "implemented"
    VALIDATING = "validating"
    VALIDATED = "validated"
    REVIEWING = "reviewing"
    DONE = "done"
    REJECTED = "rejected"
    FAILED = "failed"
    RETRYING = "retrying"


class SessionStatus(Enum):
    ACTIVE = "active"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"


# ── 合法流转表 ──────────────────────────────
# 不在这个表中的流转 → InvalidTransitionError

VALID_STORY_TRANSITIONS: dict[StoryStatus, Set[StoryStatus]] = {
    StoryStatus.PENDING:       {StoryStatus.PLANNING},
    StoryStatus.PLANNING:      {StoryStatus.PLANNED, StoryStatus.FAILED},
    StoryStatus.PLANNED:       {StoryStatus.IMPLEMENTING},
    StoryStatus.IMPLEMENTING:  {StoryStatus.IMPLEMENTED, StoryStatus.FAILED},
    StoryStatus.IMPLEMENTED:   {StoryStatus.VALIDATING},
    StoryStatus.VALIDATING:    {StoryStatus.VALIDATED, StoryStatus.FAILED},
    StoryStatus.VALIDATED:     {StoryStatus.REVIEWING},
    StoryStatus.REVIEWING:     {StoryStatus.DONE, StoryStatus.REJECTED},
    StoryStatus.REJECTED:      {StoryStatus.PLANNING},
    StoryStatus.FAILED:        {StoryStatus.RETRYING},
    StoryStatus.RETRYING:      {StoryStatus.PLANNING, StoryStatus.IMPLEMENTING, StoryStatus.VALIDATING},
    StoryStatus.DONE:          set(),  # 终态
}

VALID_SESSION_TRANSITIONS: dict[SessionStatus, Set[SessionStatus]] = {
    SessionStatus.ACTIVE:    {SessionStatus.PAUSED, SessionStatus.COMPLETED, SessionStatus.FAILED},
    SessionStatus.PAUSED:    {SessionStatus.ACTIVE, SessionStatus.FAILED},
    SessionStatus.COMPLETED: set(),
    SessionStatus.FAILED:    {SessionStatus.ACTIVE},  # 可恢复
}


class InvalidTransitionError(Exception):
    """非法状态流转异常。"""
    def __init__(self, entity_type: str, entity_id: str,
                 from_status: str, to_status: str):
        self.entity_type = entity_type
        self.entity_id = entity_id
        self.from_status = from_status
        self.to_status = to_status
        super().__init__(
            f"Illegal transition: [{entity_type}:{entity_id}] "
            f"{from_status} → {to_status}"
        )


class StateMachine:
    """故事和会话的状态机引擎。"""

    def __init__(self, event_emitter=None):
        """
        Args:
            event_emitter: 可选的事件发射器（events.EventEmitter）
        """
        self._events = event_emitter
        self._transition_log: list[dict] = []

    # ── 故事状态 ────────────────────────

    def validate_story_transition(
        self, story_id: str,
        from_status: StoryStatus,
        to_status: StoryStatus
    ) -> bool:
        """验证故事状态流转是否合法。返回 True/抛出 InvalidTransitionError。"""
        valid_targets = VALID_STORY_TRANSITIONS.get(from_status, set())
        if to_status not in valid_targets:
            raise InvalidTransitionError(
                "story", story_id,
                from_status.value, to_status.value
            )
        return True

    def transition_story(
        self, story_id: str,
        from_status: StoryStatus,
        to_status: StoryStatus,
        metadata: Optional[dict] = None
    ) -> dict:
        """执行故事状态流转。

        Returns:
            {
                "story_id": str,
                "from": str, "to": str,
                "timestamp": str,
                "valid": bool,
            }
        """
        self.validate_story_transition(story_id, from_status, to_status)

        record = {
            "entity": "story",
            "entity_id": story_id,
            "from": from_status.value,
            "to": to_status.value,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "valid": True,
            "metadata": metadata or {},
        }
        self._transition_log.append(record)

        # 发射事件
        if self._events:
            self._events.emit("status_changed", record)

        return record

    # ── 会话状态 ────────────────────────

    def validate_session_transition(
        self, session_id: str,
        from_status: SessionStatus,
        to_status: SessionStatus
    ) -> bool:
        valid_targets = VALID_SESSION_TRANSITIONS.get(from_status, set())
        if to_status not in valid_targets:
            raise InvalidTransitionError(
                "session", session_id,
                from_status.value, to_status.value
            )
        return True

    def transition_session(
        self, session_id: str,
        from_status: SessionStatus,
        to_status: SessionStatus,
        metadata: Optional[dict] = None
    ) -> dict:
        self.validate_session_transition(session_id, from_status, to_status)

        record = {
            "entity": "session",
            "entity_id": session_id,
            "from": from_status.value,
            "to": to_status.value,
            "timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "valid": True,
            "metadata": metadata or {},
        }
        self._transition_log.append(record)

        if self._events:
            self._events.emit("status_changed", record)

        return record

    # ── 便捷查询 ────────────────────────

    def can_transition(self, from_status: str, to_status: str,
                       entity: str = "story") -> bool:
        """检查流转是否合法（不抛异常）。"""
        if entity == "story":
            table = VALID_STORY_TRANSITIONS
            fs = StoryStatus(from_status)
            ts = StoryStatus(to_status)
        else:
            table = VALID_SESSION_TRANSITIONS
            fs = SessionStatus(from_status)
            ts = SessionStatus(to_status)
        return ts in table.get(fs, set())

    def next_valid_statuses(self, current_status: str,
                            entity: str = "story") -> list[str]:
        """返回当前状态下所有合法的下一步状态。"""
        if entity == "story":
            table = VALID_STORY_TRANSITIONS
            fs = StoryStatus(current_status)
        else:
            table = VALID_SESSION_TRANSITIONS
            fs = SessionStatus(current_status)
        return [s.value for s in table.get(fs, set())]

    def get_log(self) -> list[dict]:
        return list(self._transition_log)


# ── 模块级便捷函数 ──────────────────────

_default_sm = StateMachine()


def transition(from_status: str, to_status: str,
               entity: str = "story", entity_id: str = "",
               metadata: Optional[dict] = None) -> dict:
    """便捷函数：执行状态流转。"""
    sm = _default_sm
    if entity == "story":
        return sm.transition_story(
            entity_id or "unknown",
            StoryStatus(from_status),
            StoryStatus(to_status),
            metadata
        )
    else:
        return sm.transition_session(
            entity_id or "unknown",
            SessionStatus(from_status),
            SessionStatus(to_status),
            metadata
        )
