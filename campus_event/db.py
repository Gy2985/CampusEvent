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
        """数据库文件不存在时自动建表并写入演示数据；已存在时升级到当前版本。"""
        if not self.exists():
            if seed:
                self.initialize(seed=True)
            return
        self.upgrade()

    def upgrade(self) -> None:
        """把老库（baseline-v1）升级到 v2 结构；对已升级的库是幂等的。

        v2 需要的两处结构变化：
        1. ``students`` 增加 ``grade`` 列（管理员为 NULL）；
        2. ``activities.policy_type`` 的 CHECK 放宽到包含 ``GRADE_LIMITED``。
           SQLite 不支持修改 CHECK 约束，只能“建新表 → 拷数据 → 删旧表 → 改名”。
        """
        with open(SCHEMA_PATH, "r", encoding="utf-8") as fh:
            script = fh.read()

        with self.connection() as conn:
            # schema.sql 全部是 IF NOT EXISTS，对已有表无副作用（顺带补齐 v2 新表）
            conn.executescript(script)
            columns = {row["name"] for row in conn.execute("PRAGMA table_info(students)")}
            if "grade" not in columns:
                conn.execute("ALTER TABLE students ADD COLUMN grade INTEGER")
            self._backfill_demo_grades(conn)

        with self.connection() as conn:
            row = conn.execute(
                "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'activities'"
            ).fetchone()
            if row and "GRADE_LIMITED" not in (row["sql"] or ""):
                self._rebuild_activities(conn)

    @staticmethod
    def _backfill_demo_grades(conn: sqlite3.Connection) -> None:
        """给 baseline-v1 的演示账号补年级（只补我们自己的演示账号，且只补 NULL）。

        老库升级后 ``grade`` 为 NULL 会让年级限定活动“全员不可报名”，
        演示效果不好；这里按演示账号原有身份回填，属于演示数据维护，不动真实业务数据。
        """
        demo_grades = (("S001", 2), ("S002", 3), ("S003", 1))
        for student_id, grade in demo_grades:
            conn.execute(
                "UPDATE students SET grade = ? WHERE student_id = ? AND grade IS NULL",
                (grade, student_id),
            )

    @staticmethod
    def _rebuild_activities(conn: sqlite3.Connection) -> None:
        """按 SQLite 官方 12 步迁移法重建 activities 表（保留全部数据）。"""
        conn.execute("PRAGMA foreign_keys = OFF")
        try:
            conn.executescript(
                """
                CREATE TABLE activities_v2 (
                    activity_id  INTEGER PRIMARY KEY AUTOINCREMENT,
                    title        TEXT    NOT NULL,
                    category     TEXT    NOT NULL,
                    start_at     TEXT    NOT NULL,
                    location     TEXT    NOT NULL,
                    capacity     INTEGER NOT NULL CHECK (capacity > 0),
                    policy_type  TEXT    NOT NULL
                                 CHECK (policy_type IN ('DIRECT', 'APPROVAL', 'GRADE_LIMITED')),
                    created_at   TEXT    NOT NULL,
                    updated_at   TEXT    NOT NULL
                );
                INSERT INTO activities_v2
                    (activity_id, title, category, start_at, location, capacity,
                     policy_type, created_at, updated_at)
                SELECT activity_id, title, category, start_at, location, capacity,
                       policy_type, created_at, updated_at
                  FROM activities;
                DROP TABLE activities;
                ALTER TABLE activities_v2 RENAME TO activities;
                """
            )
        finally:
            conn.execute("PRAGMA foreign_keys = ON")

    def initialize(self, seed: bool = True) -> None:
        """重建数据库结构与演示数据（会删除并重建所有表，主键从头开始）。"""
        with open(SCHEMA_PATH, "r", encoding="utf-8") as fh:
            script = fh.read()
        conn = self.connect()
        try:
            conn.executescript(
                """
                DROP TABLE IF EXISTS email_outbox;
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
    # v2 / CR-01：演示学生带年级（大一/大二/大三），管理员不设年级
    students = [
        ("S001", "张三（学生A）", "student", 2),
        ("S002", "李四（学生B）", "student", 3),
        ("S003", "王五（学生C）", "student", 1),
        ("A001", "赵老师（管理员）", "admin", None),
    ]
    conn.executemany(
        "INSERT INTO students (student_id, name, role, grade) VALUES (?, ?, ?, ?)", students
    )

    created = format_dt(base)
    activities = [
        ("校园歌手大赛", "文艺", format_dt(base + timedelta(days=5, hours=2)), "大学生活动中心", 2, "DIRECT", created, created),
        ("程序设计竞赛（初赛）", "学术", format_dt(base + timedelta(days=7)), "实验楼 A305", 50, "APPROVAL", created, created),
        ("羽毛球友谊赛", "体育", format_dt(base + timedelta(days=3, hours=4)), "体育馆二层", 20, "DIRECT", created, created),
        ("软件工程前沿讲座", "讲座", format_dt(base + timedelta(days=1, hours=3)), "图书馆报告厅", 100, "APPROVAL", created, created),
        # v2 / CR-01：新增一条年级限定活动（仅大二、大三可报）
        ("职业规划工作坊（大二大三专场）", "讲座", format_dt(base + timedelta(days=6)), "就业指导中心 305", 30, "GRADE_LIMITED", created, created),
    ]
    conn.executemany(
        """
        INSERT INTO activities
            (title, category, start_at, location, capacity, policy_type, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        activities,
    )
