"""需求变更验收用例 CR1-01 ~ CR1-05、CR2-01 ~ CR2-05（v2）。

每条用例的 docstring 标注教师材料中的用例编号，便于与《07-回归测试表-v2.md》逐条对照。
"""
from __future__ import annotations

import pytest

from conftest import ADMIN, STUDENT_A, STUDENT_B, STUDENT_C, make_activity, messages_of

from campus_event import create_app
from campus_event.domain.entities import RegistrationStatus
from campus_event.domain.errors import GradeRestrictedError
from campus_event.events.events import RegistrationEvent, RegistrationEventType
from campus_event.ports.email_sender import MockEmailSender
from campus_event.repositories.email_repository import EmailRepository
from campus_event.repositories.registration_repository import RegistrationRepository


# ---------------- 测试辅助 ----------------
def add_student(db, student_id: str, name: str, grade: int, role: str = "student") -> None:
    with db.transaction() as conn:
        conn.execute(
            "INSERT INTO students (student_id, name, role, grade) VALUES (?, ?, ?, ?)",
            (student_id, name, role, grade),
        )


def emails_of(db) -> list:
    with db.connection() as conn:
        return EmailRepository(conn).list_all()


def registrations_of(db, activity_id: int) -> int:
    with db.connection() as conn:
        return RegistrationRepository(conn).count_total(activity_id)


@pytest.fixture
def app_failing_email(tmp_path):
    """邮件服务整体故障的应用实例（用于 CR2-03）。"""
    return create_app(
        {
            "DATABASE": str(tmp_path / "fail_email.db"),
            "TESTING": True,
            "SECRET_KEY": "test-key",
            "SEED_DEMO": True,
            "EMAIL_SENDER": MockEmailSender(always_fail=True),
        }
    )


# ==================== CR-01 年级限定直接报名 ====================
def test_cr1_01_sophomore_can_register(app, service, db):
    """CR1-01：大二学生报名年级限定活动 → 通过。"""
    activity = make_activity(app, title="CR1 年级限定活动", capacity=3, policy="GRADE_LIMITED")
    registration = service.register(activity.activity_id, STUDENT_A)  # S001 = 大二
    assert registration.status is RegistrationStatus.APPROVED
    assert emails_of(db)[0].status == "SENT"  # 同时触发邮件渠道（CR-02）


def test_cr1_02_junior_can_register(app, service):
    """CR1-02：大三学生报名年级限定活动 → 通过。"""
    activity = make_activity(app, title="CR1 年级限定活动-大三", capacity=3, policy="GRADE_LIMITED")
    registration = service.register(activity.activity_id, STUDENT_B)  # S002 = 大三
    assert registration.status is RegistrationStatus.APPROVED


def test_cr1_03_freshman_rejected_with_reason(app, service, db):
    """CR1-03：大一学生报名年级限定活动 → 拒绝并给出原因。"""
    activity = make_activity(app, title="CR1 年级限定活动-大一", capacity=3, policy="GRADE_LIMITED")
    with pytest.raises(GradeRestrictedError) as excinfo:
        service.register(activity.activity_id, STUDENT_C)  # S003 = 大一
    assert "仅限大二、大三" in excinfo.value.message
    assert "大一" in excinfo.value.message
    # 关键：事务回滚，不留下任何报名记录（也不污染名额/待审核数）
    assert registrations_of(db, activity.activity_id) == 0


def test_cr1_04_senior_rejected_with_reason(app, service, db):
    """CR1-04：大四学生报名年级限定活动 → 拒绝并给出原因。"""
    add_student(db, "S004", "赵六（学生D）", 4)
    activity = make_activity(app, title="CR1 年级限定活动-大四", capacity=3, policy="GRADE_LIMITED")
    with pytest.raises(GradeRestrictedError) as excinfo:
        service.register(activity.activity_id, "S004")
    assert "大四" in excinfo.value.message
    assert registrations_of(db, activity.activity_id) == 0


def test_cr1_05_legacy_policies_unchanged(app, service):
    """CR1-05：变更后原有“直接报名”“审核报名”行为不变（C1–C10 另行全量回归）。"""
    direct = make_activity(app, title="CR1 回归-直接报名", capacity=2, policy="DIRECT")
    approval = make_activity(app, title="CR1 回归-审核报名", capacity=2, policy="APPROVAL")

    assert service.register(direct.activity_id, STUDENT_C).status is RegistrationStatus.APPROVED
    assert service.register(approval.activity_id, STUDENT_C).status is RegistrationStatus.PENDING


def test_cr1_grade_limited_still_respects_capacity(app, service, db):
    """CR-01 补充：年级限定活动同样受公共名额约束（容量 1，第二人失败）。"""
    from campus_event.domain.errors import CapacityExceededError

    activity = make_activity(app, title="CR1 名额约束", capacity=1, policy="GRADE_LIMITED")
    service.register(activity.activity_id, STUDENT_A)
    with pytest.raises(CapacityExceededError):
        service.register(activity.activity_id, STUDENT_B)


def test_cr1_grade_limited_still_blocks_duplicate(app, service):
    """CR-01 补充：年级限定活动同样受“重复有效报名”约束。"""
    from campus_event.domain.errors import DuplicateRegistrationError

    activity = make_activity(app, title="CR1 重复约束", capacity=3, policy="GRADE_LIMITED")
    service.register(activity.activity_id, STUDENT_A)
    with pytest.raises(DuplicateRegistrationError):
        service.register(activity.activity_id, STUDENT_A)


# ==================== CR-02 模拟邮件通知 ====================
def test_cr2_01_direct_registration_triggers_both_channels(app, service, db):
    """CR2-01：直接报名通过 → 站内消息 + 模拟邮件都有记录。"""
    activity = make_activity(app, title="CR2 直接报名", capacity=2, policy="DIRECT")
    service.register(activity.activity_id, STUDENT_A)

    assert len(messages_of(db, STUDENT_A)) == 1
    emails = emails_of(db)
    assert len(emails) == 1
    assert emails[0].status == "SENT"
    assert emails[0].to_addr == "S001@campus.example.edu"
    assert "报名成功" in emails[0].subject
    assert "CR2 直接报名" in emails[0].subject


def test_cr2_02_approve_and_reject_send_matching_mail(app, service, db):
    """CR2-02：审核批准与拒绝 → 两种渠道分别记录对应结果。"""
    activity = make_activity(app, title="CR2 审核活动", capacity=3, policy="APPROVAL")
    pending_a = service.register(activity.activity_id, STUDENT_A)
    pending_b = service.register(activity.activity_id, STUDENT_B)

    # 待审核提交本身不发邮件（需求只覆盖"通过/拒绝"）
    assert emails_of(db) == []

    service.approve(pending_a.registration_id, ADMIN)
    service.reject(pending_b.registration_id, ADMIN, reason="名额有限")

    emails = emails_of(db)
    assert len(emails) == 2
    assert {e.status for e in emails} == {"SENT"}
    subjects = " | ".join(e.subject for e in emails)
    assert "审核通过" in subjects and "审核未通过" in subjects
    # 站内消息同样有两条结果通知（提交 2 条 + 结果 2 条 = 4）
    assert len(messages_of(db, STUDENT_A)) == 2
    assert len(messages_of(db, STUDENT_B)) == 2


def test_cr2_03_email_failure_keeps_registration_and_logs_error(app_failing_email):
    """CR2-03：模拟邮件发送失败 → 报名状态正确、错误有记录，站内消息不受影响。"""
    service = app_failing_email.extensions["registration_service"]
    db = app_failing_email.extensions["db"]
    activity = make_activity(app_failing_email, title="CR2 故障场景", capacity=2, policy="DIRECT")

    registration = service.register(activity.activity_id, STUDENT_A)

    assert registration.status is RegistrationStatus.APPROVED  # 业务没有被回滚
    emails = emails_of(db)
    assert len(emails) == 1
    assert emails[0].status == "FAILED"
    assert "SMTP" in (emails[0].error or "")
    assert len(messages_of(db, STUDENT_A)) == 1  # 另一渠道照常


def test_cr2_04_duplicate_event_sends_only_once(app, service, db):
    """CR2-04：同一业务事件重复分发 → 不产生多份相同通知（幂等）。"""
    activity = make_activity(app, title="CR2 幂等活动", capacity=2, policy="DIRECT")
    registration = service.register(activity.activity_id, STUDENT_A)

    event = RegistrationEvent(
        event_type=RegistrationEventType.SUBMITTED,
        registration_id=registration.registration_id,
        activity_id=activity.activity_id,
        student_id=STUDENT_A,
        activity_title=activity.title,
        notification_text="重复分发测试",
        occurred_at=registration.created_at,
    )
    app.extensions["event_bus"].publish(event)  # 再放两次
    app.extensions["event_bus"].publish(event)

    assert len(emails_of(db)) == 1
    assert len(messages_of(db, STUDENT_A)) == 1


def test_cr2_05_core_service_untouched(app, service):
    """CR2-05：通知渠道变化不影响核心报名服务的行为（原有流程照旧）。"""
    activity = make_activity(app, title="CR2 核心流程", capacity=1, policy="DIRECT")
    first = service.register(activity.activity_id, STUDENT_A)
    cancelled = service.cancel(first.registration_id, STUDENT_A)
    assert first.status is RegistrationStatus.APPROVED
    assert cancelled.status is RegistrationStatus.CANCELLED


# ==================== 界面与迁移 ====================
def test_web_admin_email_page(client, app):
    """界面：管理端邮件发件箱可访问并展示记录。"""
    service = app.extensions["registration_service"]
    activity = make_activity(app, title="界面邮件活动", capacity=2, policy="DIRECT")
    service.register(activity.activity_id, STUDENT_A)

    client.post("/login", data={"user_id": ADMIN})
    resp = client.get("/admin/emails")
    assert resp.status_code == 200
    assert "模拟邮件发件箱" in resp.get_data(as_text=True)


def test_web_login_shows_grade(client):
    """界面：登录页展示学生年级，便于演示 CR-01。"""
    html = client.get("/login").get_data(as_text=True)
    assert "大二" in html and "大三" in html and "大一" in html


def test_upgrade_from_v1_database(tmp_path):
    """迁移：baseline-v1 的老库能被 upgrade() 平滑升级到 v2（补 grade 列 + 重建 activities）。"""
    from campus_event.db import Database

    db_path = tmp_path / "legacy.db"
    legacy = Database(str(db_path))
    with legacy.connect() as conn:
        conn.executescript(
            """
            CREATE TABLE students (
                student_id TEXT PRIMARY KEY, name TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'student' CHECK (role IN ('student', 'admin'))
            );
            CREATE TABLE activities (
                activity_id INTEGER PRIMARY KEY AUTOINCREMENT, title TEXT NOT NULL,
                category TEXT NOT NULL, start_at TEXT NOT NULL, location TEXT NOT NULL,
                capacity INTEGER NOT NULL CHECK (capacity > 0),
                policy_type TEXT NOT NULL CHECK (policy_type IN ('DIRECT','APPROVAL')),
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            INSERT INTO students (student_id, name, role) VALUES ('S009', '老库学生', 'student');
            INSERT INTO activities (title, category, start_at, location, capacity, policy_type, created_at, updated_at)
            VALUES ('老库活动', '学术', '2026-12-01 10:00:00', '老地点', 10, 'DIRECT',
                    '2026-11-01 10:00:00', '2026-11-01 10:00:00');
            """
        )

    upgraded = Database(str(db_path))
    upgraded.upgrade()

    with upgraded.connection() as conn:
        cols = {row["name"] for row in conn.execute("PRAGMA table_info(students)")}
        assert "grade" in cols
        # 老数据没有丢
        assert conn.execute("SELECT COUNT(*) FROM activities").fetchone()[0] == 1
        # 新取值可以通过 CHECK 约束
        conn.execute(
            "INSERT INTO activities (title, category, start_at, location, capacity, policy_type, created_at, updated_at)"
            " VALUES ('年级限定', '讲座', '2026-12-02 10:00:00', '地点', 5, 'GRADE_LIMITED', 'x', 'x')"
        )
