"""边界、异常与设计约束测试（补充用例，编号 X1–X10）。"""
from __future__ import annotations

import pytest

from conftest import ADMIN, STUDENT_A, STUDENT_B, make_activity, make_past_activity, messages_of

from campus_event.domain.entities import RegistrationStatus
from campus_event.domain.errors import (
    BusinessError,
    CapacityExceededError,
    InvalidStateTransitionError,
    PermissionDeniedError,
    RegistrationClosedError,
    ValidationError,
)
from campus_event.events.events import RegistrationEvent, RegistrationEventType
from campus_event.repositories import queries
from campus_event.repositories.activity_repository import ActivityRepository
from campus_event.repositories.message_repository import MessageRepository


# ---------------- X1：活动已开始不允许报名 ----------------
def test_x1_registration_closed_after_start(app, service, db):
    activity = make_past_activity(db)
    with pytest.raises(RegistrationClosedError):
        service.register(activity.activity_id, STUDENT_A)


# ---------------- X2：已开始的活动不允许取消 ----------------
def test_x2_cancel_closed_after_start(app, service, db):
    activity = make_activity(app, title="X2 活动", capacity=2, policy="DIRECT")
    registration = service.register(activity.activity_id, STUDENT_A)

    from datetime import timedelta

    from campus_event.domain.timeutil import format_dt, now

    past = format_dt(now() - timedelta(minutes=1))
    with db.transaction() as conn:
        conn.execute(
            "UPDATE activities SET start_at = ? WHERE activity_id = ?",
            (past, activity.activity_id),
        )

    with pytest.raises(RegistrationClosedError):
        service.cancel(registration.registration_id, STUDENT_A)


# ---------------- X3：非法状态迁移 ----------------
def test_x3_cannot_cancel_rejected(app, service):
    activity = make_activity(app, title="X3 活动", capacity=2, policy="APPROVAL")
    pending = service.register(activity.activity_id, STUDENT_A)
    service.reject(pending.registration_id, ADMIN)
    with pytest.raises(InvalidStateTransitionError):
        service.cancel(pending.registration_id, STUDENT_A)


def test_x3b_cannot_approve_approved(app, service):
    activity = make_activity(app, title="X3b 活动", capacity=2, policy="APPROVAL")
    pending = service.register(activity.activity_id, STUDENT_A)
    service.approve(pending.registration_id, ADMIN)
    with pytest.raises(InvalidStateTransitionError):
        service.approve(pending.registration_id, ADMIN)


# ---------------- X4：越权操作 ----------------
def test_x4_student_cannot_approve(app, service):
    activity = make_activity(app, title="X4 活动", capacity=2, policy="APPROVAL")
    pending = service.register(activity.activity_id, STUDENT_A)
    with pytest.raises(PermissionDeniedError):
        service.approve(pending.registration_id, STUDENT_B)


def test_x4b_student_cannot_cancel_others(app, service):
    activity = make_activity(app, title="X4b 活动", capacity=2, policy="DIRECT")
    registration = service.register(activity.activity_id, STUDENT_A)
    with pytest.raises(PermissionDeniedError):
        service.cancel(registration.registration_id, STUDENT_B)


def test_x4c_admin_cannot_register(app, service):
    activity = make_activity(app, title="X4c 活动", capacity=2, policy="DIRECT")
    with pytest.raises(PermissionDeniedError):
        service.register(activity.activity_id, ADMIN)


# ---------------- X5：活动管理边界 ----------------
def test_x5_capacity_cannot_below_approved(app, service, activity_service):
    activity = make_activity(app, title="X5 活动", capacity=3, policy="DIRECT")
    service.register(activity.activity_id, STUDENT_A)
    service.register(activity.activity_id, STUDENT_B)
    with pytest.raises(ValidationError):
        activity_service.update(
            operator_id=ADMIN,
            activity_id=activity.activity_id,
            title=activity.title,
            category=activity.category,
            start_at=activity.start_at.replace(" ", "T")[:16],
            location=activity.location,
            capacity="1",
            policy_type="DIRECT",
        )


def test_x5b_delete_activity_with_registrations_refused(app, service, activity_service):
    activity = make_activity(app, title="X5b 活动", capacity=3, policy="DIRECT")
    service.register(activity.activity_id, STUDENT_A)
    with pytest.raises(BusinessError):
        activity_service.delete(ADMIN, activity.activity_id)


def test_x5c_delete_empty_activity_ok(app, activity_service):
    activity = make_activity(app, title="X5c 活动", capacity=3, policy="DIRECT")
    activity_service.delete(ADMIN, activity.activity_id)
    with app.extensions["db"].connection() as conn:
        assert ActivityRepository(conn).get(activity.activity_id) is None


def test_x5d_past_activity_cannot_be_created(activity_service):
    with pytest.raises(ValidationError):
        activity_service.create(
            operator_id=ADMIN,
            title="过去的活动",
            category="测试",
            start_at="2020-01-01T10:00",
            location="某地",
            capacity="5",
            policy_type="DIRECT",
        )


# ---------------- X6：通知幂等（不重复通知） ----------------
def test_x6_duplicate_event_notified_once(app, db):
    activity = make_activity(app, title="X6 活动", capacity=2, policy="DIRECT")
    event = RegistrationEvent(
        event_type=RegistrationEventType.SUBMITTED,
        registration_id=999,
        activity_id=activity.activity_id,
        student_id=STUDENT_A,
        activity_title=activity.title,
        notification_text="测试通知",
        occurred_at="2026-11-19 10:00:00",
    )
    bus = app.extensions["event_bus"]
    bus.publish(event)
    bus.publish(event)  # 重复发布同一事件
    assert len(messages_of(db, STUDENT_A)) == 1


# ---------------- X7：通知失败不回滚报名，且留痕 ----------------
def test_x7_notification_failure_keeps_registration(app, service, db, monkeypatch):
    activity = make_activity(app, title="X7 活动", capacity=2, policy="DIRECT")

    def boom(self, *args, **kwargs):
        raise RuntimeError("模拟站内通知写入失败")

    monkeypatch.setattr(MessageRepository, "add", boom)
    registration = service.register(activity.activity_id, STUDENT_A)

    assert registration.status is RegistrationStatus.APPROVED
    with db.connection() as conn:
        failures = queries.failure_rows(conn)
        detail = queries.activity_detail(conn, activity.activity_id)
    assert len(failures) == 1
    assert "模拟站内通知写入失败" in failures[0]["error"]
    assert detail["approved_count"] == 1  # 报名记录没有“无声消失”


# ---------------- X8：按名称筛选 ----------------
def test_x8_filter_by_title(app, db):
    make_activity(app, title="前沿讲座专场", capacity=5, policy="DIRECT")
    with db.connection() as conn:
        hits = queries.activity_overview(conn, search="讲座专场")
    assert len(hits) == 1
    assert hits[0]["title"] == "前沿讲座专场"


# ---------------- X9：统计口径（待审核不占名额） ----------------
def test_x9_stats_exclude_pending(app, service, db):
    activity = make_activity(app, title="X9 活动", capacity=1, policy="APPROVAL")
    service.register(activity.activity_id, STUDENT_A)
    service.register(activity.activity_id, STUDENT_B)  # 满员后仍可排队
    with db.connection() as conn:
        detail = queries.activity_detail(conn, activity.activity_id)
    assert detail["approved_count"] == 0
    assert detail["pending_count"] == 2
    assert detail["remaining"] == 1
    assert detail["is_full"] is False


# ---------------- X10：已拒绝/已取消后允许再次申请 ----------------
def test_x10_reapply_after_cancel(app, service, db):
    activity = make_activity(app, title="X10 活动", capacity=1, policy="DIRECT")
    first = service.register(activity.activity_id, STUDENT_A)
    service.cancel(first.registration_id, STUDENT_A)
    second = service.register(activity.activity_id, STUDENT_A)

    assert second.status is RegistrationStatus.APPROVED
    with db.connection() as conn:
        rows = queries.student_registration_rows(conn, STUDENT_A)
    assert {row["status"] for row in rows} == {"CANCELLED", "APPROVED"}
