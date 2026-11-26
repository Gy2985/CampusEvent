"""仓储：模拟邮件发件箱（email_outbox，v2 / CR-02）。

写入策略是"先占位、后完结"：

1. ``reserve`` 用唯一键 ``dedupe_key`` 插入一条 ``QUEUED`` 记录；
2. 发送成功后 ``mark_result(SENT)``，失败则 ``mark_result(FAILED, error)``。

好处：即使同一业务事件被重复分发（重放、并发、观察者重注册），第二次 ``reserve``
会被唯一索引拒绝，从数据库层保证"同一事件只发一封"。
"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True)
class EmailRecord:
    email_id: int
    dedupe_key: str
    to_addr: str
    subject: str
    body: str
    status: str
    error: str | None
    created_at: str


class EmailRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def reserve(
        self,
        dedupe_key: str,
        to_addr: str,
        subject: str,
        body: str,
        created_at: str,
    ) -> bool:
        """占位。返回 True 表示本次是新占位，False 表示命中幂等键、已被占用。"""
        cursor = self.conn.execute(
            """
            INSERT OR IGNORE INTO email_outbox
                (dedupe_key, to_addr, subject, body, status, error, created_at)
            VALUES (?, ?, ?, ?, 'QUEUED', NULL, ?)
            """,
            (dedupe_key, to_addr, subject, body, created_at),
        )
        return cursor.rowcount > 0

    def mark_result(self, dedupe_key: str, status: str, error: str | None = None) -> None:
        self.conn.execute(
            "UPDATE email_outbox SET status = ?, error = ? WHERE dedupe_key = ?",
            (status, error, dedupe_key),
        )

    def get(self, dedupe_key: str) -> EmailRecord | None:
        row = self.conn.execute(
            "SELECT * FROM email_outbox WHERE dedupe_key = ?", (dedupe_key,)
        ).fetchone()
        return _to_record(row) if row else None

    def list_all(self) -> list[EmailRecord]:
        rows = self.conn.execute(
            "SELECT * FROM email_outbox ORDER BY email_id DESC"
        ).fetchall()
        return [_to_record(row) for row in rows]

    def count(self, status: str | None = None) -> int:
        if status is None:
            row = self.conn.execute("SELECT COUNT(*) AS c FROM email_outbox").fetchone()
        else:
            row = self.conn.execute(
                "SELECT COUNT(*) AS c FROM email_outbox WHERE status = ?", (status,)
            ).fetchone()
        return int(row["c"])


def _to_record(row: sqlite3.Row) -> EmailRecord:
    return EmailRecord(
        email_id=row["email_id"],
        dedupe_key=row["dedupe_key"],
        to_addr=row["to_addr"],
        subject=row["subject"],
        body=row["body"],
        status=row["status"],
        error=row["error"],
        created_at=row["created_at"],
    )
