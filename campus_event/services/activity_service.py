"""活动管理服务（管理员创建、编辑、删除活动）。"""
from __future__ import annotations

from datetime import datetime
from typing import Callable

from ..db import Database
from ..domain.entities import Activity, PolicyType, RegistrationStatus, Role
from ..domain.errors import (
    BusinessError,
    NotFoundError,
    PermissionDeniedError,
    ValidationError,
)
from ..domain.timeutil import format_dt, now as default_clock, parse_user_input
from ..repositories.activity_repository import ActivityRepository
from ..repositories.registration_repository import RegistrationRepository
from ..repositories.student_repository import StudentRepository


class ActivityService:
    def __init__(self, db: Database, clock: Callable[[], datetime] = default_clock):
        self.db = db
        self.clock = clock

    def create(
        self,
        operator_id: str,
        title: str,
        category: str,
        start_at: str,
        location: str,
        capacity: str,
        policy_type: str,
    ) -> Activity:
        fields = self._validate(title, category, start_at, location, capacity, policy_type)
        with self.db.transaction() as conn:
            self._require_admin(conn, operator_id)
            if fields["start_dt"] < self.clock():
                raise ValidationError("活动的开始时间必须晚于当前时间。")
            activity = ActivityRepository(conn).create(
                title=fields["title"],
                category=fields["category"],
                start_at=format_dt(fields["start_dt"]),
                location=fields["location"],
                capacity=fields["capacity"],
                policy_type=fields["policy_type"],
                timestamp=format_dt(self.clock()),
            )
        return activity

    def update(
        self,
        operator_id: str,
        activity_id: int,
        title: str,
        category: str,
        start_at: str,
        location: str,
        capacity: str,
        policy_type: str,
    ) -> Activity:
        fields = self._validate(title, category, start_at, location, capacity, policy_type)
        with self.db.transaction() as conn:
            self._require_admin(conn, operator_id)
            activity = ActivityRepository(conn).get(activity_id)
            if activity is None:
                raise NotFoundError("活动不存在或已被删除。")
            approved_count = RegistrationRepository(conn).count_by_status(
                activity_id, RegistrationStatus.APPROVED
            )
            # 边界规则：下调容量不得低于已通过人数，否则等于让纪录“超员”
            if fields["capacity"] < approved_count:
                raise ValidationError(
                    f"人数上限不能小于当前已通过人数（{approved_count} 人）。"
                )
            updated = ActivityRepository(conn).update(
                activity_id=activity_id,
                title=fields["title"],
                category=fields["category"],
                start_at=format_dt(fields["start_dt"]),
                location=fields["location"],
                capacity=fields["capacity"],
                policy_type=fields["policy_type"],
                timestamp=format_dt(self.clock()),
            )
        return updated

    def delete(self, operator_id: str, activity_id: int) -> None:
        """删除活动：已有报名记录时拒绝删除并提示（不做软删除）。"""
        with self.db.transaction() as conn:
            self._require_admin(conn, operator_id)
            activity = ActivityRepository(conn).get(activity_id)
            if activity is None:
                raise NotFoundError("活动不存在或已被删除。")
            total = RegistrationRepository(conn).count_total(activity_id)
            if total > 0:
                raise BusinessError(
                    f"该活动已有 {total} 条报名记录，不能直接删除；"
                    "请保留活动或先让学生取消报名。"
                )
            ActivityRepository(conn).delete(activity_id)

    # ---------------- 内部校验 ----------------
    def _validate(
        self,
        title: str,
        category: str,
        start_at: str,
        location: str,
        capacity: str,
        policy_type: str,
    ) -> dict:
        title = (title or "").strip()
        category = (category or "").strip()
        location = (location or "").strip()
        if not title:
            raise ValidationError("活动名称不能为空。")
        if len(title) > 60:
            raise ValidationError("活动名称不能超过 60 个字。")
        if not category:
            raise ValidationError("活动类型不能为空。")
        if not location:
            raise ValidationError("活动地点不能为空。")
        try:
            start_dt = parse_user_input(start_at)
        except ValueError:
            raise ValidationError("开始时间格式不正确。")

        try:
            capacity_value = int(str(capacity).strip())
        except (TypeError, ValueError):
            raise ValidationError("人数上限必须是正整数。")
        if capacity_value <= 0:
            raise ValidationError("人数上限必须为大于 0 的正整数。")

        try:
            policy = PolicyType(policy_type)
        except ValueError:
            raise ValidationError("报名方式只能是“直接报名”或“管理员审核”。")

        return {
            "title": title,
            "category": category,
            "location": location,
            "start_dt": start_dt,
            "capacity": capacity_value,
            "policy_type": policy,
        }

    @staticmethod
    def _require_admin(conn, operator_id: str) -> None:
        student = StudentRepository(conn).get(operator_id)
        if student is None:
            raise NotFoundError("账号不存在。")
        if student.role is not Role.ADMIN:
            raise PermissionDeniedError("只有管理员可以管理活动。")
