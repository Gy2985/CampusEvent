"""邮件通知观察者（v2 / CR-02）。

与站内通知观察者**并列**订阅同一个事件总线，互不依赖：

* 站内消息：保证"站内可见"；
* 模拟邮件：保证"邮箱可见"，故障时不回滚业务、只留痕。

三条硬约束的落实方式：
1. **不写进 RegistrationService**：本类是独立观察者，服务层一行未改；
2. **失败不回滚**：事件在数据库事务提交之后才发布，且本类吞掉异常只记录；
3. **不重复发送**：``EMAIL:{事件幂等键}`` + ``email_outbox.dedupe_key`` 唯一索引。
"""
from __future__ import annotations

import logging

from ..db import Database
from ..events.events import RegistrationEvent, RegistrationEventType
from ..domain.entities import RegistrationStatus
from ..ports.email_sender import EmailDeliveryError, EmailMessage
from ..repositories.email_repository import EmailRepository
from ..repositories.registration_repository import RegistrationRepository

logger = logging.getLogger(__name__)


class EmailNotificationObserver:
    def __init__(self, db: Database, sender):
        self.db = db
        self.sender = sender

    # ---------------- 事件入口 ----------------
    def handle(self, event: RegistrationEvent) -> None:
        try:
            status = self._status_of(event.registration_id)
            if not self._should_send(event, status):
                return

            subject, body = self._compose(event, status)
            dedupe_key = f"EMAIL:{event.dedupe_key}"
            to_addr = self._address_of(event.student_id)

            with self.db.transaction() as conn:
                reserved = EmailRepository(conn).reserve(
                    dedupe_key=dedupe_key,
                    to_addr=to_addr,
                    subject=subject,
                    body=body,
                    created_at=event.occurred_at,
                )
            if not reserved:
                logger.info("重复邮件已忽略：%s", dedupe_key)
                return

            try:
                self.sender.send(EmailMessage(to_addr=to_addr, subject=subject, body=body))
            except Exception as exc:  # 邮件渠道故障：只留痕，不影响报名与站内通知
                logger.error("模拟邮件发送失败 %s：%s", dedupe_key, exc)
                self._finish(dedupe_key, "FAILED", f"{type(exc).__name__}: {exc}")
            else:
                self._finish(dedupe_key, "SENT")
                logger.info("模拟邮件已发送 %s -> %s", dedupe_key, to_addr)
        except Exception:  # 兜底：本观察者的任何意外都不应影响其它观察者
            logger.exception("邮件观察者处理事件失败：%s", event.dedupe_key)

    # ---------------- 内部工具 ----------------
    def _should_send(self, event: RegistrationEvent, status: RegistrationStatus | None) -> bool:
        if event.event_type in (RegistrationEventType.APPROVED, RegistrationEventType.REJECTED):
            return True
        # 直接报名/年级限定报名在提交时即"已通过"；审核型报名提交时只是待审核，不发邮件
        return (
            event.event_type is RegistrationEventType.SUBMITTED
            and status is RegistrationStatus.APPROVED
        )

    def _status_of(self, registration_id: int) -> RegistrationStatus | None:
        with self.db.connection() as conn:
            registration = RegistrationRepository(conn).get(registration_id)
        return registration.status if registration else None

    @staticmethod
    def _address_of(student_id: str) -> str:
        """演示环境没有真实邮箱，按账号生成稳定可达的模拟地址。"""
        return f"{student_id}@campus.example.edu"

    @staticmethod
    def _compose(
        event: RegistrationEvent, status: RegistrationStatus | None
    ) -> tuple[str, str]:
        if event.event_type is RegistrationEventType.APPROVED:
            subject = f"【CampusEvent】审核通过：{event.activity_title}"
            headline = "您报名的活动已审核通过，请按时参加。"
        elif event.event_type is RegistrationEventType.REJECTED:
            subject = f"【CampusEvent】审核未通过：{event.activity_title}"
            headline = "您报名的活动未通过审核。"
        else:
            subject = f"【CampusEvent】报名成功：{event.activity_title}"
            headline = "报名已自动通过，请按时参加。"

        body = "\n".join(
            [
                f"同学您好：",
                f"",
                f"{headline}",
                f"活动名称：{event.activity_title}",
                f"通知内容：{event.notification_text}",
                f"报名单号：{event.registration_id}",
                f"时间：{event.occurred_at}",
                f"",
                f"（本邮件由 CampusEvent 模拟发送器发出，仅用于课程实验，不会真正投递。）",
            ]
        )
        return subject, body

    def _finish(self, dedupe_key: str, status: str, error: str | None = None) -> None:
        try:
            with self.db.transaction() as conn:
                EmailRepository(conn).mark_result(dedupe_key, status, error)
        except Exception:
            logger.exception("邮件结果回写失败：%s", dedupe_key)


__all__ = ["EmailNotificationObserver", "EmailDeliveryError"]
