"""
事件系统 — Agent 运行全生命周期事件流。

所有状态变更、门禁结果、会话事件统一通过此系统，
确保「发生了什么」可追踪、可复现。
"""

from enum import Enum
from dataclasses import dataclass, field
from typing import Callable, Optional
import datetime
import json


class EventType(Enum):
    # 故事生命周期
    STORY_STARTED = "story_started"
    PLAN_GENERATED = "plan_generated"
    CODE_COMMITTED = "code_committed"

    # 门禁
    GATE_EXECUTED = "gate_executed"
    GATE_PASSED = "gate_passed"
    GATE_FAILED = "gate_failed"

    # 状态流转
    STATUS_CHANGED = "status_changed"

    # PR
    PR_CREATED = "pr_created"

    # 恢复
    RECOVERY_STARTED = "recovery_started"
    RECOVERY_DONE = "recovery_done"
    RECOVERY_FAILED = "recovery_failed"
    FAILURE_CLASSIFIED = "failure_classified"
    ROLLBACK_PLANNED = "rollback_planned"
    RETRY_DECIDED = "retry_decided"

    # 会话
    SESSION_STARTED = "session_started"
    SESSION_ENDED = "session_ended"

    # 系统
    ERROR = "error"
    WARNING = "warning"


@dataclass
class Event:
    type: EventType
    session_id: str
    data: dict = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.datetime.now(
        datetime.timezone.utc).isoformat())
    source: str = ""  # agent role: planner/executor/reviewer/verifier

    def to_dict(self) -> dict:
        return {
            "type": self.type.value,
            "session_id": self.session_id,
            "data": self.data,
            "timestamp": self.timestamp,
            "source": self.source,
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False)


# ── 事件发射器 ────────────────────────────

Subscriber = Callable[[Event], None]


class EventEmitter:
    """发布-订阅事件总线。"""

    def __init__(self):
        self._subscribers: dict[EventType, list[Subscriber]] = {
            et: [] for et in EventType
        }
        self._all_subscribers: list[Subscriber] = []
        self._event_log: list[Event] = []

    def on(self, event_type: EventType, handler: Subscriber) -> None:
        """订阅特定事件类型。"""
        self._subscribers[event_type].append(handler)

    def on_any(self, handler: Subscriber) -> None:
        """订阅所有事件。用于审计日志等全局监听。"""
        self._all_subscribers.append(handler)

    def emit(self, event_type, data: dict = None,
             session_id: str = "", source: str = "") -> Event:
        """发射事件。通知所有订阅者。接受 EventType 或字符串。"""
        if isinstance(event_type, str):
            event_type = EventType(event_type)
        event = Event(
            type=event_type,
            session_id=session_id,
            data=data or {},
            source=source,
        )
        self._event_log.append(event)

        # 通知特定订阅者
        for handler in self._subscribers.get(event_type, []):
            try:
                handler(event)
            except Exception:
                pass  # 订阅者不应阻断事件流

        # 通知全局订阅者
        for handler in self._all_subscribers:
            try:
                handler(event)
            except Exception:
                pass

        return event

    def get_log(self, event_type: Optional[EventType] = None) -> list[Event]:
        """获取事件日志，可按类型过滤。"""
        if event_type:
            return [e for e in self._event_log if e.type == event_type]
        return list(self._event_log)

    def clear_log(self) -> None:
        self._event_log.clear()


# ── 预置订阅者 ────────────────────────────

class AuditLogWriter:
    """审计日志写入器 — 订阅所有事件，写入 JSONL 文件。"""

    def __init__(self, log_path: str = "mcps/audit_log.jsonl"):
        self.log_path = log_path

    def __call__(self, event: Event) -> None:
        try:
            with open(self.log_path, "a", encoding="utf-8") as f:
                f.write(event.to_json() + "\n")
        except Exception:
            pass  # 审计日志写入失败不应影响主流程


class ConsoleReporter:
    """控制台报告器 — 关键事件打印到 stdout。"""

    REPORT_EVENTS = {
        EventType.GATE_FAILED,
        EventType.RECOVERY_STARTED,
        EventType.RECOVERY_FAILED,
        EventType.ERROR,
    }

    def __call__(self, event: Event) -> None:
        if event.type in self.REPORT_EVENTS:
            print(f"[{event.type.value.upper()}] "
                  f"session={event.session_id} "
                  f"source={event.source} "
                  f"data={event.data}")


# ── 全局实例 ──────────────────────────────

emitter = EventEmitter()

# 默认挂载审计日志写入器
audit_writer = AuditLogWriter()
emitter.on_any(audit_writer)

# 默认挂载控制台报告器
console_reporter = ConsoleReporter()
emitter.on_any(console_reporter)


def emit(event_type, data: dict = None,
         session_id: str = "", source: str = "") -> Event:
    """便捷函数：发射事件。接受 EventType 或字符串。"""
    return emitter.emit(event_type, data, session_id, source)


# ── 自测 ──────────────────────────────────

if __name__ == "__main__":
    test_emitter = EventEmitter()

    received = []
    test_emitter.on(EventType.STATUS_CHANGED, lambda e: received.append(e))

    evt = test_emitter.emit(
        EventType.STATUS_CHANGED,
        {"story_id": "s1", "from": "pending", "to": "planning"},
        session_id="test-session",
        source="planner",
    )

    assert len(received) == 1
    assert received[0].data["story_id"] == "s1"
    assert received[0].source == "planner"

    print("[PASS] EventEmitter tests passed!")
    print(f"  Event log: {len(test_emitter.get_log())} events")
    print(f"  Filtered: {len(test_emitter.get_log(EventType.STATUS_CHANGED))} status_changed")
