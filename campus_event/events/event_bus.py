"""进程内事件总线（观察者模式中的 Subject / 主题）。

约定：
* 事件在**业务事务提交之后**发布，因此通知失败不会回滚已经合法的报名记录；
* 单个观察者抛出异常不影响其他观察者，异常记入日志，由通知观察者负责留痕；
* 同步分发即可满足单机版需求，不引入消息队列（实验要求明确不要求 MQ）。
"""
from __future__ import annotations

import logging
from typing import Callable

from .events import RegistrationEvent

logger = logging.getLogger(__name__)

EventHandler = Callable[[RegistrationEvent], None]


class EventBus:
    def __init__(self) -> None:
        self._handlers: list[EventHandler] = []

    def subscribe(self, handler: EventHandler) -> None:
        self._handlers.append(handler)

    def publish(self, event: RegistrationEvent) -> None:
        logger.info(
            "发布事件 type=%s registration_id=%s", event.event_type.value, event.registration_id
        )
        for handler in list(self._handlers):
            try:
                handler(event)
            except Exception:  # 单点失败不影响业务与其它观察者
                logger.exception("事件处理器执行失败：%s", event.dedupe_key)
