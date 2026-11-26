"""领域实体与枚举。

实体只描述数据与自身不变量，不包含数据库访问、事务和通知等基础设施逻辑。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from .timeutil import display, parse_dt


class RegistrationStatus(str, Enum):
    """报名状态：待审核、已通过、已拒绝、已取消。"""

    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    CANCELLED = "CANCELLED"

    @property
    def label(self) -> str:
        return _STATUS_LABELS[self]

    @property
    def is_active(self) -> bool:
        """有效报名：占用“重复报名”名额检查的两种状态。"""
        return self in (RegistrationStatus.PENDING, RegistrationStatus.APPROVED)


_STATUS_LABELS = {
    RegistrationStatus.PENDING: "待审核",
    RegistrationStatus.APPROVED: "已通过",
    RegistrationStatus.REJECTED: "已拒绝",
    RegistrationStatus.CANCELLED: "已取消",
}


class PolicyType(str, Enum):
    """活动报名方式（v2 新增年级限定直接报名）。"""

    DIRECT = "DIRECT"
    APPROVAL = "APPROVAL"
    GRADE_LIMITED = "GRADE_LIMITED"

    @property
    def label(self) -> str:
        return _POLICY_LABELS[self]

    @property
    def hint(self) -> str:
        """给页面用的一句话说明。"""
        return _POLICY_HINTS[self]


_POLICY_LABELS = {
    PolicyType.DIRECT: "直接报名",
    PolicyType.APPROVAL: "管理员审核",
    PolicyType.GRADE_LIMITED: "年级限定报名",
}

_POLICY_HINTS = {
    PolicyType.DIRECT: "提交后自动通过",
    PolicyType.APPROVAL: "提交后需管理员审核",
    PolicyType.GRADE_LIMITED: "仅限大二、大三学生，提交后自动通过",
}


class Role(str, Enum):
    STUDENT = "student"
    ADMIN = "admin"


@dataclass(frozen=True)
class Student:
    student_id: str
    name: str
    role: Role
    grade: int | None = None  # v2：1–4，管理员为 None

    @property
    def is_admin(self) -> bool:
        return self.role is Role.ADMIN

    @property
    def grade_label(self) -> str:
        if self.grade is None:
            return "—"
        return _GRADE_LABELS.get(self.grade, f"年级{self.grade}")


_GRADE_LABELS = {1: "大一", 2: "大二", 3: "大三", 4: "大四"}


@dataclass(frozen=True)
class Activity:
    activity_id: int
    title: str
    category: str
    start_at: str
    location: str
    capacity: int
    policy_type: PolicyType
    created_at: str
    updated_at: str

    @property
    def start_time(self) -> datetime:
        return parse_dt(self.start_at)

    @property
    def start_display(self) -> str:
        return display(self.start_at)


@dataclass(frozen=True)
class Registration:
    registration_id: int
    activity_id: int
    student_id: str
    status: RegistrationStatus
    created_at: str
    updated_at: str

    @property
    def status_label(self) -> str:
        return self.status.label


@dataclass(frozen=True)
class Message:
    message_id: int
    student_id: str
    activity_id: int | None
    content: str
    created_at: str
    is_read: bool


@dataclass(frozen=True)
class ActivityStats:
    """活动名额统计（P2-F08）。"""

    activity_id: int
    capacity: int
    approved_count: int
    pending_count: int

    @property
    def remaining(self) -> int:
        return max(self.capacity - self.approved_count, 0)

    @property
    def is_full(self) -> bool:
        return self.approved_count >= self.capacity
