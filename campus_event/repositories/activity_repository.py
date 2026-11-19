"""仓储：活动（Activity）。"""
from __future__ import annotations

import sqlite3

from ..domain.entities import Activity, PolicyType


class ActivityRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def get(self, activity_id: int) -> Activity | None:
        row = self.conn.execute(
            "SELECT * FROM activities WHERE activity_id = ?", (activity_id,)
        ).fetchone()
        return _to_activity(row) if row else None

    def list_all(self) -> list[Activity]:
        rows = self.conn.execute(
            "SELECT * FROM activities ORDER BY start_at ASC, activity_id ASC"
        ).fetchall()
        return [_to_activity(row) for row in rows]

    def create(
        self,
        title: str,
        category: str,
        start_at: str,
        location: str,
        capacity: int,
        policy_type: PolicyType,
        timestamp: str,
    ) -> Activity:
        cursor = self.conn.execute(
            """
            INSERT INTO activities
                (title, category, start_at, location, capacity, policy_type, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (title, category, start_at, location, capacity, policy_type.value, timestamp, timestamp),
        )
        activity_id = int(cursor.lastrowid)
        activity = self.get(activity_id)
        assert activity is not None
        return activity

    def update(
        self,
        activity_id: int,
        title: str,
        category: str,
        start_at: str,
        location: str,
        capacity: int,
        policy_type: PolicyType,
        timestamp: str,
    ) -> Activity:
        self.conn.execute(
            """
            UPDATE activities
               SET title = ?, category = ?, start_at = ?, location = ?,
                   capacity = ?, policy_type = ?, updated_at = ?
             WHERE activity_id = ?
            """,
            (title, category, start_at, location, capacity, policy_type.value, timestamp, activity_id),
        )
        activity = self.get(activity_id)
        assert activity is not None
        return activity

    def delete(self, activity_id: int) -> None:
        self.conn.execute("DELETE FROM activities WHERE activity_id = ?", (activity_id,))


def _to_activity(row: sqlite3.Row) -> Activity:
    return Activity(
        activity_id=row["activity_id"],
        title=row["title"],
        category=row["category"],
        start_at=row["start_at"],
        location=row["location"],
        capacity=row["capacity"],
        policy_type=PolicyType(row["policy_type"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )
