"""Web 层冒烟测试：登录、页面渲染、表单校验、权限拦截。"""
from __future__ import annotations

from conftest import ADMIN, STUDENT_A, make_activity


def login(client, user_id: str):
    return client.post("/login", data={"user_id": user_id}, follow_redirects=False)


def test_login_page_lists_demo_accounts(client):
    resp = client.get("/login")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "张三" in body and "赵老师" in body


def test_requires_login(client):
    resp = client.get("/activities")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_student_login_and_list(client, app):
    login(client, STUDENT_A)
    resp = client.get("/activities")
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "校园活动列表" in body
    assert "程序设计竞赛" in body


def test_student_register_via_ui(client, app, db):
    login(client, STUDENT_A)
    activity = make_activity(app, title="界面报名活动", capacity=2, policy="DIRECT")

    resp = client.post(f"/activities/{activity.activity_id}/register", follow_redirects=True)
    assert resp.status_code == 200
    body = resp.get_data(as_text=True)
    assert "我的状态" in body
    assert "已通过" in body

    messages_page = client.get("/messages").get_data(as_text=True)
    assert "报名成功" in messages_page


def test_filter_by_keyword(client, app):
    login(client, STUDENT_A)
    resp = client.get("/activities?q=讲座")
    body = resp.get_data(as_text=True)
    assert "软件工程前沿讲座" in body
    assert "羽毛球友谊赛" not in body


def test_admin_pages(client, app):
    login(client, ADMIN)
    resp = client.get("/admin/activities")
    assert resp.status_code == 200
    assert "活动管理" in resp.get_data(as_text=True)

    resp = client.get("/admin/reviews")
    assert resp.status_code == 200
    assert "待审核报名" in resp.get_data(as_text=True)

    resp = client.get("/admin/failures")
    assert resp.status_code == 200
    assert "通知失败留痕" in resp.get_data(as_text=True)


def test_student_cannot_open_admin_page(client, app):
    login(client, STUDENT_A)
    resp = client.get("/admin/activities")
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/activities")


def test_create_activity_validation_error(client, app):
    login(client, ADMIN)
    resp = client.post(
        "/admin/activities/new",
        data={
            "title": "",
            "category": "学术",
            "start_at": "2030-01-01T09:00",
            "location": "某地",
            "capacity": "10",
            "policy_type": "DIRECT",
        },
    )
    assert resp.status_code == 200
    assert "活动名称不能为空" in resp.get_data(as_text=True)


def test_create_activity_success(client, app, db):
    login(client, ADMIN)
    resp = client.post(
        "/admin/activities/new",
        data={
            "title": "新建测试活动",
            "category": "学术",
            "start_at": "2030-01-01T09:00",
            "location": "报告厅",
            "capacity": "10",
            "policy_type": "APPROVAL",
        },
        follow_redirects=True,
    )
    assert "活动创建成功" in resp.get_data(as_text=True)
    assert "新建测试活动" in resp.get_data(as_text=True)


def test_admin_approve_via_ui(client, app, service):
    activity = make_activity(app, title="界面审批活动", capacity=2, policy="APPROVAL")

    student_client = app.test_client()
    login(student_client, STUDENT_A)
    student_client.post(f"/activities/{activity.activity_id}/register", follow_redirects=True)

    admin_client = app.test_client()
    login(admin_client, ADMIN)
    pending_page = admin_client.get("/admin/reviews").get_data(as_text=True)
    assert "界面审批活动" in pending_page

    from campus_event.repositories import queries

    with app.extensions["db"].connection() as conn:
        pending = queries.pending_registration_rows(conn, activity.activity_id)
    resp = admin_client.post(
        f"/admin/registrations/{pending[0]['registration_id']}/approve", follow_redirects=True
    )
    assert "已批准报名" in resp.get_data(as_text=True)
