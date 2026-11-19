"""仓储：报名记录（Registration）。"""
from __future__ import annotations

import sqlite3

from ..domain.entities import Registration, RegistrationStatus


class RegistrationRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def get(self, registration_id: int) -> Registration | None:
        row = self.conn.execute(
            "SELECT * FROM registrations WHERE registration_id = ?", (registration_id,)
        ).fetchone()
        return _to_registration(row) if row else None

    def create(
        self, activity_id: int, student_id: str, status: RegistrationStatus, timestamp: str
    ) -> Registration:
        cursor = self.conn.execute(
            """
            INSERT INTO registrations (activity_id, student_id, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (activity_id, student_id, status.value, timestamp, timestamp),
        )
        registration = self.get(int(cursor.lastrowid))
        assert registration is not None
        return registration

    def update_status(
        self, registration_id: int, status: RegistrationStatus, timestamp: str
    ) -> Registration:
        self.conn.execute(
            "UPDATE registrations SET status = ?, updated_at = ? WHERE registration_id = ?",
            (status.value, timestamp, registration_id),
        )
        registration = self.get(registration_id)
        assert registration is not None
        return registration

    def find_active(self, activity_id: int, student_id: str) -> Registration | None:
        """查找同活动下的有效报名（待审核或已通过）。"""
        row = self.conn.execute(
            """
            SELECT * FROM registrations
             WHERE activity_id = ? AND student_id = ?
               AND status IN ('PENDING', 'APPROVED')
             ORDER BY registration_id DESC
             LIMIT 1
            """,
            (activity_id, student_id),
        ).fetchone()
        return _to_registration(row) if row else None

    def my_status(self, activity_id: int, student_id: str) -> RegistrationStatus | None:
        row = self.conn.execute(
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

    def count_by_status(self, activity_id: int, status: RegistrationStatus) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) AS c FROM registrations WHERE activity_id = ? AND status = ?",
            (activity_id, status.value),
        ).fetchone()
        return int(row["c"])

    def count_total(self, activity_id: int) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) AS c FROM registrations WHERE activity_id = ?", (activity_id,)
        ).fetchone()
        return int(row["c"])

    def list_by_activity(
        self, activity_id: int, status: RegistrationStatus | None = None
    ) -> list[Registration]:
        if status is None:
            rows = self.conn.execute(
                "SELECT * FROM registrations WHERE activity_id = ? ORDER BY registration_id",
                (activity_id,),
            ).fetchall()
        else:
            rows = self.conn.execute(
                "SELECT * FROM registrations WHERE activity_id = ? AND status = ? ORDER BY registration_id",
                (activity_id, status.value),
            ).fetchall()
        return [_to_registration(row) for row in rows]

    def list_by_student(self, student_id: str) -> list[Registration]:
        rows = self.conn.execute(
            "SELECT * FROM registrations WHERE student_id = ? ORDER BY registration_id DESC",
            (student_id,),
        ).fetchall()
        return [_to_registration(row) for row in rows]


def _to_registration(row: sqlite3.Row) -> Registration:
    return Registration(
        registration_id=row["registration_id"],
        activity_id=row["activity_id"],
        student_id=row["student_id"],
        status=RegistrationStatus(row["status"]),
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )
