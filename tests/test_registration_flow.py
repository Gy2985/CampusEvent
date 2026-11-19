"""初始版本核心验收用例 C1–C10（对应指导书 3.5 节）。

每条测试的 docstring 标注对应用例编号与验收点，便于与回归测试表一一对照。
"""
from __future__ import annotations

import pytest

from conftest import (
    ADMIN,
    STUDENT_A,
    STUDENT_B,
    STUDENT_C,
    make_activity,
    messages_of,
)

from campus_event.domain.entities import RegistrationStatus


# ---------------- C1：创建直接报名活动 ----------------
def test_c1_create_direct_activity(app, activity_service):
    """C1：管理员创建直接报名活动，容量 2 → 创建成功，可供学生报名。"""
    activity = make_activity(app, title="C1 直接报名活动", capacity=2, policy="DIRECT")
    assert activity.activity_id > 0
    assert activity.capacity == 2
    assert activity.policy_type.value == "DIRECT"
    assert activity.start_time > __import__("datetime").datetime.now()


# ---------------- C2：直接报名自动通过并通知 ----------------
def test_c2_direct_registration_approved_and_notified(app, service, db):
    """C2：学生A报名直接报名活动 → 直接变为“已通过”，并生成站内通知。"""
    activity = make_activity(app, title="C2 活动", capacity=2, policy="DIRECT")
    registration = service.register(activity.activity_id, STUDENT_A)

    assert registration.status is RegistrationStatus.APPROVED
    messages = messages_of(db, STUDENT_A)
    assert len(messages) == 1
    assert "报名成功" in messages[0].content
    assert messages[0].activity_id == activity.activity_id


# ---------------- C3：拒绝重复有效报名 ----------------
def test_c3_duplicate_registration_rejected(app, service):
    """C3：学生A再次提交相同活动报名 → 拒绝重复有效报名。"""
    from campus_event.domain.errors import DuplicateRegistrationError

    activity = make_activity(app, title="C3 活动", capacity=5, policy="DIRECT")
    service.register(activity.activity_id, STUDENT_A)

    with pytest.raises(DuplicateRegistrationError):
        service.register(activity.activity_id, STUDENT_A)


# ---------------- C4：名额满后第三人失败 ----------------
def test_c4_capacity_full_third_student_fails(app, service, db):
    """C4：容量 2 的活动，A、B 通过，C 报名因名额不足失败。"""
    from campus_event.domain.errors import CapacityExceededError

    activity = make_activity(app, title="C4 活动", capacity=2, policy="DIRECT")
    a = service.register(activity.activity_id, STUDENT_A)
    b = service.register(activity.activity_id, STUDENT_B)
    assert a.status is RegistrationStatus.APPROVED
    assert b.status is RegistrationStatus.APPROVED

    with pytest.raises(CapacityExceededError):
        service.register(activity.activity_id, STUDENT_C)

    from campus_event.repositories.registration_repository import RegistrationRepository

    with db.connection() as conn:
        approved = RegistrationRepository(conn).count_by_status(
            activity.activity_id, RegistrationStatus.APPROVED
        )
    assert approved == 2  # 没有产生第 3 条已通过记录


# ---------------- C5：审核型活动进入待审核 ----------------
def test_c5_approval_activity_pending(app, service):
    """C5：创建审核型活动，学生A申请 → 状态为“待审核”，不占名额。"""
    activity = make_activity(app, title="C5 活动", capacity=2, policy="APPROVAL")
    registration = service.register(activity.activity_id, STUDENT_A)

    assert registration.status is RegistrationStatus.PENDING
    from campus_event.repositories.registration_repository import RegistrationRepository

    with app.extensions["db"].connection() as conn:
        approved = RegistrationRepository(conn).count_by_status(
            activity.activity_id, RegistrationStatus.APPROVED
        )
    assert approved == 0


# ---------------- C6：批准生成已通过与通知 ----------------
def test_c6_approve_sets_approved_and_notifies(app, service, db):
    """C6：管理员批准 A 的待审核报名 → 变为“已通过”且生成通知。"""
    activity = make_activity(app, title="C6 活动", capacity=3, policy="APPROVAL")
    pending = service.register(activity.activity_id, STUDENT_A)
    approved = service.approve(pending.registration_id, ADMIN)

    assert approved.status is RegistrationStatus.APPROVED
    messages = messages_of(db, STUDENT_A)
    assert len(messages) == 2  # 提交通知 + 批准通知
    assert any("审核已通过" in m.content for m in messages)


# ---------------- C7：拒绝生成已拒绝与通知 ----------------
def test_c7_reject_sets_rejected_and_notifies(app, service, db):
    """C7：管理员拒绝另一待审核报名 → 变为“已拒绝”且生成通知。"""
    activity = make_activity(app, title="C7 活动", capacity=3, policy="APPROVAL")
    pending = service.register(activity.activity_id, STUDENT_B)
    rejected = service.reject(pending.registration_id, ADMIN, reason="名额优先给高年级")

    assert rejected.status is RegistrationStatus.REJECTED
    messages = messages_of(db, STUDENT_B)
    assert any("审核未通过" in m.content and "名额优先给高年级" in m.content for m in messages)


# ---------------- C8：满员时批准失败 ----------------
def test_c8_approve_when_full_fails(app, service, db):
    """C8：批准时容量已满 → 批准失败，不超出人数上限。"""
    from campus_event.domain.errors import CapacityExceededError

    activity = make_activity(app, title="C8 活动", capacity=1, policy="APPROVAL")
    a = service.register(activity.activity_id, STUDENT_A)
    b = service.register(activity.activity_id, STUDENT_B)

    service.approve(a.registration_id, ADMIN)
    with pytest.raises(CapacityExceededError):
        service.approve(b.registration_id, ADMIN)

    from campus_event.repositories.registration_repository import RegistrationRepository

    with db.connection() as conn:
        approved = RegistrationRepository(conn).count_by_status(
            activity.activity_id, RegistrationStatus.APPROVED
        )
        pending = RegistrationRepository(conn).count_by_status(
            activity.activity_id, RegistrationStatus.PENDING
        )
    assert approved == 1
    assert pending == 1  # B 仍是待审核，状态没有被破坏


# ---------------- C9：取消报名与统计同步 ----------------
def test_c9_cancel_updates_status_and_stats(app, service, db):
    """C9：学生取消已通过报名 → 状态“已取消”，已通过数同步减少。"""
    activity = make_activity(app, title="C9 活动", capacity=2, policy="DIRECT")
    registration = service.register(activity.activity_id, STUDENT_A)
    cancelled = service.cancel(registration.registration_id, STUDENT_A)

    assert cancelled.status is RegistrationStatus.CANCELLED

    from campus_event.repositories import queries

    with db.connection() as conn:
        detail = queries.activity_detail(conn, activity.activity_id, STUDENT_A)
    assert detail["approved_count"] == 0
    assert detail["remaining"] == 2
    assert detail["my_status"] == "CANCELLED"


# ---------------- C10：重启后数据一致 ----------------
def test_c10_restart_keeps_data(app, service, db):
    """C10：重新启动服务（重建应用、复用同一数据库文件）后，活动/报名/通知仍一致。"""
    from campus_event import create_app
    from campus_event.repositories import queries

    activity = make_activity(app, title="C10 活动", capacity=3, policy="APPROVAL")
    registration = service.register(activity.activity_id, STUDENT_A)
    service.approve(registration.registration_id, ADMIN)

    db_path = db.path
    new_app = create_app(
        {"DATABASE": db_path, "TESTING": True, "SECRET_KEY": "test-key", "SEED_DEMO": False}
    )
    with new_app.extensions["db"].connection() as conn:
        detail = queries.activity_detail(conn, activity.activity_id, STUDENT_A)
        rows = queries.student_registration_rows(conn, STUDENT_A)
        msgs = queries.message_rows(conn, STUDENT_A)
    assert detail["approved_count"] == 1
    assert len(rows) == 1 and rows[0]["status"] == "APPROVED"
    assert len(msgs) == 2
