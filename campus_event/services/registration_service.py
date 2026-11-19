"""报名业务服务：把领域对象、策略与事件总线组装起来。

事务边界：一次 ``register`` / ``cancel`` / ``approve`` / ``reject`` 调用
= 一个数据库事务；事务提交后才发布事件，通知失败不会让报名记录“无声消失”。
"""
from __future__ import annotations

from typing import Callable

from ..db import Database
from ..domain.entities import (
    Activity,
    Registration,
    RegistrationStatus,
    Role,
    Student,
)
from ..domain.errors import (
    CapacityExceededError,
    DuplicateRegistrationError,
    InvalidStateTransitionError,
    NotFoundError,
    PermissionDeniedError,
    RegistrationClosedError,
    ValidationError,
)
from ..domain.timeutil import format_dt, now as default_clock
from ..events.event_bus import EventBus
from ..events.events import RegistrationEvent, RegistrationEventType
from ..policies.base import RegistrationContext
from ..policies.implementations import PolicyRegistry
from ..repositories.activity_repository import ActivityRepository
from ..repositories.registration_repository import RegistrationRepository
from ..repositories.student_repository import StudentRepository


class RegistrationService:
    def __init__(
        self,
        db: Database,
        policies: PolicyRegistry,
        event_bus: EventBus,
        clock: Callable[[], object] = default_clock,
    ):
        self.db = db
        self.policies = policies
        self.event_bus = event_bus
        self.clock = clock

    # ---------------- 学生报名 ----------------
    def register(self, activity_id: int, student_id: str) -> Registration:
        with self.db.transaction() as conn:
            student = self._get_student(conn, student_id)
            if student.role is Role.ADMIN:
                raise PermissionDeniedError("管理员账号不参与活动报名。")
            activity = self._get_activity(conn, activity_id)
            current = self.clock()

            # 公共规则 1：活动开始后不允许报名
            if activity.start_time < current:
                raise RegistrationClosedError("活动已经开始，无法报名。")

            registrations = RegistrationRepository(conn)
            # 公共规则 2：同一活动不允许重复有效报名
            if registrations.find_active(activity_id, student_id):
                raise DuplicateRegistrationError("您已报名该活动（待审核或已通过），不能重复报名。")

            approved_count = registrations.count_by_status(activity_id, RegistrationStatus.APPROVED)
            policy = self.policies.get(activity.policy_type)
            context = RegistrationContext(
                activity=activity, student=student, approved_count=approved_count, now=current
            )

            # 公共规则 3：名额上限；是否“立即检查”由策略声明
            if policy.requires_immediate_capacity_check and context.is_full:
                raise CapacityExceededError(
                    f"名额已满（上限 {activity.capacity} 人），无法报名。"
                )

            decision = policy.decide(context)
            registration = registrations.create(
                activity_id=activity_id,
                student_id=student_id,
                status=decision.status,
                timestamp=format_dt(current),
            )

        self._publish(
            RegistrationEventType.SUBMITTED,
            registration,
            activity,
            decision.student_message,
            format_dt(current),
        )
        return registration

    # ---------------- 学生取消 ----------------
    def cancel(self, registration_id: int, student_id: str) -> Registration:
        with self.db.transaction() as conn:
            activity, registration = self._get_activity_of_registration(conn, registration_id)
            if registration.student_id != student_id:
                raise PermissionDeniedError("只能取消自己的报名。")
            if registration.status not in (RegistrationStatus.PENDING, RegistrationStatus.APPROVED):
                raise InvalidStateTransitionError(
                    f"当前报名状态为“{registration.status.label}”，不能取消。"
                )
            current = self.clock()
            if activity.start_time < current:
                raise RegistrationClosedError("活动已经开始，无法取消报名。")

            updated = RegistrationRepository(conn).update_status(
                registration_id, RegistrationStatus.CANCELLED, format_dt(current)
            )

        self._publish(
            RegistrationEventType.CANCELLED,
            updated,
            activity,
            f"您已取消活动《{activity.title}》的报名。",
            format_dt(current),
        )
        return updated

    # ---------------- 管理员审批 ----------------
    def approve(self, registration_id: int, operator_id: str) -> Registration:
        with self.db.transaction() as conn:
            self._require_admin(conn, operator_id)
            activity, registration = self._get_activity_of_registration(conn, registration_id)
            if registration.status is not RegistrationStatus.PENDING:
                raise InvalidStateTransitionError(
                    f"当前报名状态为“{registration.status.label}”，只有待审核报名可以批准。"
                )
            approved_count = RegistrationRepository(conn).count_by_status(
                activity.activity_id, RegistrationStatus.APPROVED
            )
            # 审批冲突处理：批准时再次检查名额，满员不得批准
            if approved_count >= activity.capacity:
                raise CapacityExceededError(
                    f"名额已满（上限 {activity.capacity} 人），本次批准失败。"
                )
            current = self.clock()
            updated = RegistrationRepository(conn).update_status(
                registration_id, RegistrationStatus.APPROVED, format_dt(current)
            )

        self._publish(
            RegistrationEventType.APPROVED,
            updated,
            activity,
            f"好消息！您报名的活动《{activity.title}》审核已通过。",
            format_dt(current),
        )
        return updated

    def reject(self, registration_id: int, operator_id: str, reason: str = "") -> Registration:
        with self.db.transaction() as conn:
            self._require_admin(conn, operator_id)
            activity, registration = self._get_activity_of_registration(conn, registration_id)
            if registration.status is not RegistrationStatus.PENDING:
                raise InvalidStateTransitionError(
                    f"当前报名状态为“{registration.status.label}”，只有待审核报名可以拒绝。"
                )
            current = self.clock()
            updated = RegistrationRepository(conn).update_status(
                registration_id, RegistrationStatus.REJECTED, format_dt(current)
            )

        text = f"很遗憾，您报名的活动《{activity.title}》审核未通过。"
        if reason:
            text += f"原因：{reason}"
        self._publish(
            RegistrationEventType.REJECTED, updated, activity, text, format_dt(current)
        )
        return updated

    # ---------------- 内部工具 ----------------
    def _publish(
        self,
        event_type: RegistrationEventType,
        registration: Registration,
        activity: Activity,
        notification_text: str,
        occurred_at: str,
    ) -> None:
        self.event_bus.publish(
            RegistrationEvent(
                event_type=event_type,
                registration_id=registration.registration_id,
                activity_id=activity.activity_id,
                student_id=registration.student_id,
                activity_title=activity.title,
                notification_text=notification_text,
                occurred_at=occurred_at,
            )
        )

    @staticmethod
    def _get_student(conn, student_id: str) -> Student:
        student = StudentRepository(conn).get(student_id)
        if student is None:
            raise NotFoundError("账号不存在。")
        return student

    @staticmethod
    def _require_admin(conn, operator_id: str) -> Student:
        student = StudentRepository(conn).get(operator_id)
        if student is None:
            raise NotFoundError("账号不存在。")
        if student.role is not Role.ADMIN:
            raise PermissionDeniedError("只有管理员可以执行审批操作。")
        return student

    @staticmethod
    def _get_activity(conn, activity_id: int) -> Activity:
        activity = ActivityRepository(conn).get(activity_id)
        if activity is None:
            raise NotFoundError("活动不存在或已被删除。")
        return activity

    def _get_activity_of_registration(self, conn, registration_id: int) -> tuple[Activity, Registration]:
        registration = RegistrationRepository(conn).get(registration_id)
        if registration is None:
            raise NotFoundError("报名记录不存在。")
        activity = self._get_activity(conn, registration.activity_id)
        return activity, registration

    @staticmethod
    def validate_capacity(raw: str) -> int:
        try:
            capacity = int(str(raw).strip())
        except (TypeError, ValueError):
            raise ValidationError("人数上限必须是正整数。")
        if capacity <= 0:
            raise ValidationError("人数上限必须为正整数且大于 0。")
        return capacity
