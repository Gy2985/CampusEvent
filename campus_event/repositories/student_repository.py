"""仓储：学生账号。"""
from __future__ import annotations

import sqlite3

from ..domain.entities import Role, Student


class StudentRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def get(self, student_id: str) -> Student | None:
        row = self.conn.execute(
            "SELECT student_id, name, role FROM students WHERE student_id = ?", (student_id,)
        ).fetchone()
        return _to_student(row) if row else None

    def list_all(self) -> list[Student]:
        rows = self.conn.execute(
            "SELECT student_id, name, role FROM students ORDER BY role DESC, student_id"
        ).fetchall()
        return [_to_student(row) for row in rows]


def _to_student(row: sqlite3.Row) -> Student:
    return Student(student_id=row["student_id"], name=row["name"], role=Role(row["role"]))
