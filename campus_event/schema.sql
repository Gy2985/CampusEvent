-- CampusEvent 初始版本数据库结构（SQLite）
-- 说明：容量、状态、角色等约束在数据库层再做一次兜底校验，
--      但“名额不超限”“不允许重复有效报名”等核心业务规则由服务层判断，
--      数据库约束只作为最后一道防线。

CREATE TABLE IF NOT EXISTS students (
    student_id TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    role       TEXT NOT NULL DEFAULT 'student'
               CHECK (role IN ('student', 'admin')),
    -- v2 / CR-01：学生年级 1–4（管理员不参与报名，允许为 NULL）
    grade      INTEGER CHECK (grade BETWEEN 1 AND 4)
);

CREATE TABLE IF NOT EXISTS activities (
    activity_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    title        TEXT    NOT NULL,
    category     TEXT    NOT NULL,
    start_at     TEXT    NOT NULL,
    location     TEXT    NOT NULL,
    capacity     INTEGER NOT NULL CHECK (capacity > 0),
    -- v2 / CR-01：报名方式扩展出 'GRADE_LIMITED'（年级限定直接报名）
    policy_type  TEXT    NOT NULL
                 CHECK (policy_type IN ('DIRECT', 'APPROVAL', 'GRADE_LIMITED')),
    created_at   TEXT    NOT NULL,
    updated_at   TEXT    NOT NULL
);

CREATE TABLE IF NOT EXISTS registrations (
    registration_id INTEGER PRIMARY KEY AUTOINCREMENT,
    activity_id     INTEGER NOT NULL REFERENCES activities (activity_id) ON DELETE RESTRICT,
    student_id      TEXT    NOT NULL REFERENCES students (student_id),
    status          TEXT    NOT NULL
                    CHECK (status IN ('PENDING', 'APPROVED', 'REJECTED', 'CANCELLED')),
    created_at      TEXT    NOT NULL,
    updated_at      TEXT    NOT NULL
);

-- 同一学生对同一活动最多只能有一条“待审核/已通过”的有效报名；
-- 已取消、已拒绝作为历史记录保留，因此允许再次申请。
CREATE UNIQUE INDEX IF NOT EXISTS ux_registration_active
    ON registrations (activity_id, student_id)
    WHERE status IN ('PENDING', 'APPROVED');

CREATE INDEX IF NOT EXISTS ix_registration_activity ON registrations (activity_id, status);

CREATE TABLE IF NOT EXISTS messages (
    message_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    student_id  TEXT    NOT NULL REFERENCES students (student_id),
    activity_id INTEGER,
    content     TEXT    NOT NULL,
    created_at  TEXT    NOT NULL,
    is_read     INTEGER NOT NULL DEFAULT 0 CHECK (is_read IN (0, 1)),
    -- 幂等键：同一业务事件只写入一条通知，避免重复通知
    dedupe_key  TEXT    UNIQUE
);

CREATE TABLE IF NOT EXISTS notification_failures (
    failure_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    event_type  TEXT    NOT NULL,
    registration_id INTEGER,
    activity_id INTEGER,
    student_id  TEXT,
    message     TEXT,
    error       TEXT    NOT NULL,
    created_at  TEXT    NOT NULL
);

-- v2 / CR-02：模拟邮件发件箱
-- 先占位（QUEUED）再完结（SENT / FAILED），dedupe_key 唯一即可保证“同一业务事件只发一封”
CREATE TABLE IF NOT EXISTS email_outbox (
    email_id   INTEGER PRIMARY KEY AUTOINCREMENT,
    dedupe_key TEXT    NOT NULL UNIQUE,
    to_addr    TEXT    NOT NULL,
    subject    TEXT    NOT NULL,
    body       TEXT    NOT NULL,
    status     TEXT    NOT NULL DEFAULT 'QUEUED'
                       CHECK (status IN ('QUEUED', 'SENT', 'FAILED')),
    error      TEXT,
    created_at TEXT    NOT NULL
);
