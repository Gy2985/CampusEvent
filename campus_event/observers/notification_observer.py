"""站内通知观察者。

职责：监听报名领域事件，把通知写入 ``messages`` 表。
设计要点：
* 通知失败**不影响**已提交的报名事务：报名先提交，事件后发布；
* 失败写入 ``notification_failures`` 表 + 日志，保证“有迹可循”，可人工补发；
* 借助 ``dedupe_key`` 唯一索引实现幂等，避免同一事件重复通知。
"""
from __future__ import annotations

import logging

from ..db import Database
from ..domain.timeutil import now
from ..events.events import RegistrationEvent
from ..repositories.failure_repository import FailureRepository
from ..repositories.message_repository import MessageRepository

logger = logging.getLogger(__name__)


class NotificationObserver:
    def __init__(self, db: Database):
        self.db = db

    def handle(self, event: RegistrationEvent) -> None:
        try:
            with self.db.transaction() as conn:
                inserted = MessageRepository(conn).add(
                    student_id=event.student_id,
                    activity_id=event.activity_id,
                    content=event.notification_text,
                    created_at=event.occurred_at,
                    dedupe_key=event.dedupe_key,
                )
            if not inserted:
                logger.info("重复通知已忽略：%s", event.dedupe_key)
        except Exception as exc:  # 通知渠道故障：留痕，不抛出
            logger.error("站内通知写入失败 %s：%s", event.dedupe_key, exc)
            self._record_failure(event, exc)

    def _record_failure(self, event: RegistrationEvent, exc: Exception) -> None:
        try:
            with self.db.transaction() as conn:
                FailureRepository(conn).record(
                    event_type=event.event_type.value,
                    registration_id=event.registration_id,
                    activity_id=event.activity_id,
                    student_id=event.student_id,
                    message=event.notification_text,
                    error=f"{type(exc).__name__}: {exc}",
                    created_at=now().strftime("%Y-%m-%d %H:%M:%S"),
                )
        except Exception:
            logger.exception("通知失败留痕也失败了：%s", event.dedupe_key)
