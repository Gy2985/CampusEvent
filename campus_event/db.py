"""SQLite 连接与事务管理。

设计要点：
1. 连接使用 ``isolation_level=None``（自动提交模式），事务由 ``transaction()``
   显式控制，做到“业务方法自己决定事务边界”，而不是隐式地在每个 execute 提交。
2. ``transaction()`` 使用 ``BEGIN IMMEDIATE``，在报名、审批这类会读写名额计数的
   场景中尽早获得写锁，降低“两个学生同时抢最后一个名额”的并发风险。
3. 仓储对象随事务连接创建，保证一次业务操作内的多条 SQL 处于同一事务。
"""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from datetime import timedelta
from typing import Iterator

from .domain.timeutil import format_dt, now

SCHEMA_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schema.sql")


class Database:
    def __init__(self, path: str):
        self.path = os.path.abspath(path)

    # ---------- 连接与事务 ----------
    def connect(self) -> sqlite3.Connection:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        conn = sqlite3.connect(self.path, isolation_level=None, timeout=10)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        """只读场景：自动提交模式下的普通连接。"""
        conn = self.connect()
        try:
            yield conn
        finally:
            conn.close()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """写场景：显式开启事务，异常时整体回滚。"""
        conn = self.connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            yield conn
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()

    # ---------- 初始化 ----------
    def exists(self) -> bool:
        return os.path.exists(self.path)

    def ensure_ready(self, seed: bool = True) -> None:
        """数据库文件不存在时自动建表并写入演示数据。"""
        if seed and not self.exists():
            self.initialize(seed=True)

    def initialize(self, seed: bool = True) -> None:
        """重建数据库结构与演示数据（会删除并重建所有表，主键从头开始）。"""
        with open(SCHEMA_PATH, "r", encoding="utf-8") as fh:
            script = fh.read()
        conn = self.connect()
        try:
            conn.executescript(
                """
                DROP TABLE IF EXISTS notification_failures;
                DROP TABLE IF EXISTS messages;
                DROP TABLE IF EXISTS registrations;
                DROP TABLE IF EXISTS activities;
                DROP TABLE IF EXISTS students;
                """
            )
            conn.executescript(script)
            if seed:
                _seed_demo_data(conn)
        finally:
            conn.close()


def _seed_demo_data(conn: sqlite3.Connection) -> None:
    """写入固定演示账号与示例活动（时间基于当前日期，保证演示始终可用）。"""
    base = now()
    students = [
        ("S001", "张三（学生A）", "student"),
        ("S002", "李四（学生B）", "student"),
        ("S003", "王五（学生C）", "student"),
        ("A001", "赵老师（管理员）", "admin"),
    ]
    conn.executemany(
        "INSERT INTO students (student_id, name, role) VALUES (?, ?, ?)", students
    )

    created = format_dt(base)
    activities = [
        ("校园歌手大赛", "文艺", format_dt(base + timedelta(days=5, hours=2)), "大学生活动中心", 2, "DIRECT", created, created),
        ("程序设计竞赛（初赛）", "学术", format_dt(base + timedelta(days=7)), "实验楼 A305", 50, "APPROVAL", created, created),
        ("羽毛球友谊赛", "体育", format_dt(base + timedelta(days=3, hours=4)), "体育馆二层", 20, "DIRECT", created, created),
        ("软件工程前沿讲座", "讲座", format_dt(base + timedelta(days=1, hours=3)), "图书馆报告厅", 100, "APPROVAL", created, created),
    ]
    conn.executemany(
        """
        INSERT INTO activities
            (title, category, start_at, location, capacity, policy_type, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        activities,
    )
