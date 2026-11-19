"""仓储：站内消息（Message）。"""
from __future__ import annotations

import sqlite3

from ..domain.entities import Message


class MessageRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def add(
        self,
        student_id: str,
        activity_id: int | None,
        content: str,
        created_at: str,
        dedupe_key: str | None = None,
    ) -> bool:
        """写入一条站内消息。

        返回 True 表示真正写入，False 表示命中唯一幂等键、被忽略。
        ``INSERT OR IGNORE`` + ``dedupe_key`` 唯一索引共同保证“同一业务事件
        不会产生两条重复通知”。
        """
        cursor = self.conn.execute(
            """
            INSERT OR IGNORE INTO messages
                (student_id, activity_id, content, created_at, is_read, dedupe_key)
            VALUES (?, ?, ?, ?, 0, ?)
            """,
            (student_id, activity_id, content, created_at, dedupe_key),
        )
        return cursor.rowcount > 0

    def list_for_student(self, student_id: str) -> list[Message]:
        rows = self.conn.execute(
            """
            SELECT * FROM messages WHERE student_id = ?
             ORDER BY is_read ASC, message_id DESC
            """,
            (student_id,),
        ).fetchall()
        return [
            Message(
                message_id=row["message_id"],
                student_id=row["student_id"],
                activity_id=row["activity_id"],
                content=row["content"],
                created_at=row["created_at"],
                is_read=bool(row["is_read"]),
            )
            for row in rows
        ]

    def unread_count(self, student_id: str) -> int:
        row = self.conn.execute(
            "SELECT COUNT(*) AS c FROM messages WHERE student_id = ? AND is_read = 0",
            (student_id,),
        ).fetchone()
        return int(row["c"])

    def mark_read(self, student_id: str) -> int:
        cursor = self.conn.execute(
            "UPDATE messages SET is_read = 1 WHERE student_id = ? AND is_read = 0",
            (student_id,),
        )
        return cursor.rowcount
