"""读模型（面向页面展示的查询）。

领域仓储只返回实体，页面需要的“活动 + 统计 + 我的报名状态”这类跨表视图
统一放在这里，避免把展示逻辑塞进业务服务，也避免页面直接写 SQL。
"""
from __future__ import annotations

import sqlite3

from ..domain.entities import PolicyType, RegistrationStatus
from ..domain.timeutil import display, now, parse_dt


def activity_overview(
    conn: sqlite3.Connection, search: str | None = None, student_id: str | None = None
) -> list[dict]:
    """活动列表：含已通过数、待审核数、剩余名额与“我的报名状态”。"""
    sql = """
        SELECT a.*,
               (SELECT COUNT(*) FROM registrations r
                 WHERE r.activity_id = a.activity_id AND r.status = 'APPROVED') AS approved_count,
               (SELECT COUNT(*) FROM registrations r
                 WHERE r.activity_id = a.activity_id AND r.status = 'PENDING') AS pending_count
          FROM activities a
    """
    params: list[object] = []
    if search:
        sql += " WHERE a.title LIKE ?"
        params.append(f"%{search}%")
    sql += " ORDER BY a.start_at ASC, a.activity_id ASC"

    rows = conn.execute(sql, params).fetchall()
    current = now()
    result = []
    for row in rows:
        item = _activity_dict(row)
        item["started"] = parse_dt(row["start_at"]) < current
        if student_id:
            status = _my_status(conn, row["activity_id"], student_id)
            item["my_status"] = status.value if status else None
            item["my_status_label"] = status.label if status else None
        result.append(item)
    return result


def activity_detail(
    conn: sqlite3.Connection, activity_id: int, student_id: str | None = None
) -> dict | None:
    row = conn.execute(
        """
        SELECT a.*,
               (SELECT COUNT(*) FROM registrations r
                 WHERE r.activity_id = a.activity_id AND r.status = 'APPROVED') AS approved_count,
               (SELECT COUNT(*) FROM registrations r
                 WHERE r.activity_id = a.activity_id AND r.status = 'PENDING') AS pending_count
          FROM activities a WHERE a.activity_id = ?
        """,
        (activity_id,),
    ).fetchone()
    if row is None:
        return None
    item = _activity_dict(row)
    item["started"] = parse_dt(row["start_at"]) < now()
    if student_id:
        registration_ref = _my_registration(conn, activity_id, student_id)
        item["my_status"] = registration_ref[0].value if registration_ref else None
        item["my_status_label"] = registration_ref[0].label if registration_ref else None
        item["my_registration_id"] = registration_ref[1] if registration_ref else None
    return item


def activity_registration_rows(conn: sqlite3.Connection, activity_id: int) -> list[dict]:
    """活动详情页的报名名单（管理员视角）。"""
    rows = conn.execute(
        """
        SELECT r.registration_id, r.status, r.created_at, s.name AS student_name, s.student_id
          FROM registrations r JOIN students s ON s.student_id = r.student_id
         WHERE r.activity_id = ?
         ORDER BY CASE r.status WHEN 'PENDING' THEN 0 WHEN 'APPROVED' THEN 1 ELSE 2 END,
                  r.registration_id
        """,
        (activity_id,),
    ).fetchall()
    return [
        {
            "registration_id": row["registration_id"],
            "student_id": row["student_id"],
            "student_name": row["student_name"],
            "status": row["status"],
            "status_label": RegistrationStatus(row["status"]).label,
            "created_at": display(row["created_at"]),
        }
        for row in rows
    ]


def student_registration_rows(conn: sqlite3.Connection, student_id: str) -> list[dict]:
    """我的报名：报名记录 + 活动信息。"""
    rows = conn.execute(
        """
        SELECT r.registration_id, r.status, r.created_at, r.activity_id,
               a.title, a.start_at, a.location, a.category
          FROM registrations r JOIN activities a ON a.activity_id = r.activity_id
         WHERE r.student_id = ?
         ORDER BY r.registration_id DESC
        """,
        (student_id,),
    ).fetchall()
    return [
        {
            "registration_id": row["registration_id"],
            "activity_id": row["activity_id"],
            "title": row["title"],
            "category": row["category"],
            "location": row["location"],
            "start_display": display(row["start_at"]),
            "status": row["status"],
            "status_label": RegistrationStatus(row["status"]).label,
            "created_at": display(row["created_at"]),
            "can_cancel": row["status"] in ("PENDING", "APPROVED")
            and parse_dt(row["start_at"]) >= now(),
        }
        for row in rows
    ]


def pending_registration_rows(conn: sqlite3.Connection, activity_id: int | None = None) -> list[dict]:
    """待审核列表（管理员视角）。"""
    sql = """
        SELECT r.registration_id, r.activity_id, r.student_id, r.created_at,
               s.name AS student_name, a.title, a.start_at
          FROM registrations r
          JOIN students s ON s.student_id = r.student_id
          JOIN activities a ON a.activity_id = r.activity_id
         WHERE r.status = 'PENDING'
    """
    params: list[object] = []
    if activity_id is not None:
        sql += " AND r.activity_id = ?"
        params.append(activity_id)
    sql += " ORDER BY r.registration_id"
    rows = conn.execute(sql, params).fetchall()
    return [
        {
            "registration_id": row["registration_id"],
            "activity_id": row["activity_id"],
            "student_id": row["student_id"],
            "student_name": row["student_name"],
            "title": row["title"],
            "start_display": display(row["start_at"]),
            "created_at": display(row["created_at"]),
        }
        for row in rows
    ]


def message_rows(conn: sqlite3.Connection, student_id: str) -> list[dict]:
    rows = conn.execute(
        """
        SELECT m.*, a.title FROM messages m
          LEFT JOIN activities a ON a.activity_id = m.activity_id
         WHERE m.student_id = ?
         ORDER BY m.is_read ASC, m.message_id DESC
        """,
        (student_id,),
    ).fetchall()
    return [
        {
            "message_id": row["message_id"],
            "content": row["content"],
            "title": row["title"],
            "created_at": display(row["created_at"]),
            "is_read": bool(row["is_read"]),
        }
        for row in rows
    ]


def failure_rows(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    return conn.execute("SELECT * FROM notification_failures ORDER BY failure_id DESC").fetchall()


def _my_status(
    conn: sqlite3.Connection, activity_id: int, student_id: str
) -> RegistrationStatus | None:
    row = conn.execute(
        """
        SELECT status FROM registrations
         WHERE activity_id = ? AND student_id = ?
         ORDER BY CASE status WHEN 'APPROVED' THEN 0 WHEN 'PENDING' THEN 1 ELSE 2 END,
                  registration_id DESC
         LIMIT 1
        """,
        (activity_id, student_id),
    ).fetchone()
    return RegistrationStatus(row["status"]) if row else None


def _my_registration(
    conn: sqlite3.Connection, activity_id: int, student_id: str
) -> tuple[RegistrationStatus, int] | None:
    """返回“我在该活动上最相关的一条报名”（有效报名优先，其次最近历史）。"""
    row = conn.execute(
        """
        SELECT status, registration_id FROM registrations
         WHERE activity_id = ? AND student_id = ?
         ORDER BY CASE status WHEN 'APPROVED' THEN 0 WHEN 'PENDING' THEN 1 ELSE 2 END,
                  registration_id DESC
         LIMIT 1
        """,
        (activity_id, student_id),
    ).fetchone()
    if row is None:
        return None
    return RegistrationStatus(row["status"]), int(row["registration_id"])


def _activity_dict(row: sqlite3.Row) -> dict:
    approved = int(row["approved_count"])
    pending = int(row["pending_count"])
    capacity = int(row["capacity"])
    policy = PolicyType(row["policy_type"])
    return {
        "activity_id": row["activity_id"],
        "title": row["title"],
        "category": row["category"],
        "start_at": row["start_at"],
        "start_display": display(row["start_at"]),
        "location": row["location"],
        "capacity": capacity,
        "policy_type": policy.value,
        "policy_label": policy.label,
        "approved_count": approved,
        "pending_count": pending,
        "remaining": max(capacity - approved, 0),
        "is_full": approved >= capacity,
        "my_status": None,
        "my_status_label": None,
    }
