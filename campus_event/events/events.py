"""领域事件定义（观察者模式中的“事件”）。

事件只携带“已经发生的事实”和通知所需的最小信息；
通知的具体措辞由服务层构造，观察者只负责分发到具体通知渠道。
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class RegistrationEventType(str, Enum):
    SUBMITTED = "SUBMITTED"   # 报名已提交（可能是已通过或待审核）
    APPROVED = "APPROVED"     # 管理员批准
    REJECTED = "REJECTED"     # 管理员拒绝
    CANCELLED = "CANCELLED"   # 学生取消


@dataclass(frozen=True)
class RegistrationEvent:
    event_type: RegistrationEventType
    registration_id: int
    activity_id: int
    student_id: str
    activity_title: str
    notification_text: str
    occurred_at: str

    @property
    def dedupe_key(self) -> str:
        """幂等键：同一报名记录的同一类事件只会通知一次。"""
        return f"{self.event_type.value}:{self.registration_id}"
