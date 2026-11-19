"""仓储：通知失败留痕。"""
from __future__ import annotations

import sqlite3


class FailureRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def record(
        self,
        event_type: str,
        registration_id: int | None,
        activity_id: int | None,
        student_id: str | None,
        message: str,
        error: str,
        created_at: str,
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO notification_failures
                (event_type, registration_id, activity_id, student_id, message, error, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (event_type, registration_id, activity_id, student_id, message, error, created_at),
        )

    def list_all(self) -> list[sqlite3.Row]:
        return self.conn.execute(
            "SELECT * FROM notification_failures ORDER BY failure_id DESC"
        ).fetchall()
