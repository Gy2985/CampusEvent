"""pytest 公共夹具与测试辅助函数。"""
from __future__ import annotations

import os
import sys

import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from campus_event import create_app  # noqa: E402
from campus_event.db import Database  # noqa: E402
from campus_event.domain.timeutil import now  # noqa: E402
from campus_event.repositories.activity_repository import ActivityRepository  # noqa: E402
from campus_event.repositories.message_repository import MessageRepository  # noqa: E402

ADMIN = "A001"
STUDENT_A = "S001"
STUDENT_B = "S002"
STUDENT_C = "S003"


@pytest.fixture
def app(tmp_path):
    return create_app(
        {
            "DATABASE": str(tmp_path / "test_campus.db"),
            "TESTING": True,
            "SECRET_KEY": "test-key",
            "SEED_DEMO": True,
        }
    )


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def db(app) -> Database:
    return app.extensions["db"]


@pytest.fixture
def service(app):
    return app.extensions["registration_service"]


@pytest.fixture
def activity_service(app):
    return app.extensions["activity_service"]


def make_activity(
    app,
    title="测试活动",
    capacity=2,
    policy="DIRECT",
    start_in_days=3,
    category="学术",
):
    """用活动服务创建一个活动，返回活动实体。"""
    from datetime import timedelta

    service = app.extensions["activity_service"]
    start_at = (now() + timedelta(days=start_in_days)).strftime("%Y-%m-%dT%H:%M")
    return service.create(
        operator_id=ADMIN,
        title=title,
        category=category,
        start_at=start_at,
        location="测试地点",
        capacity=str(capacity),
        policy_type=policy,
    )


def make_past_activity(db: Database, title="已开始的活动", capacity=5, policy="DIRECT"):
    """直接落库构造一个“已开始”的活动，绕过创建时的未来时间校验。"""
    from datetime import timedelta

    from campus_event.domain.entities import PolicyType
    from campus_event.domain.timeutil import format_dt

    past = format_dt(now() - timedelta(hours=2))
    with db.transaction() as conn:
        return ActivityRepository(conn).create(
            title=title,
            category="测试",
            start_at=past,
            location="旧地点",
            capacity=capacity,
            policy_type=PolicyType(policy),
            timestamp=past,
        )


def messages_of(db: Database, student_id: str) -> list:
    with db.connection() as conn:
        return MessageRepository(conn).list_for_student(student_id)
