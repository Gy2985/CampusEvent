-- CampusEvent 初始版本数据库结构（SQLite）
-- 说明：容量、状态、角色等约束在数据库层再做一次兜底校验，
--      但“名额不超限”“不允许重复有效报名”等核心业务规则由服务层判断，
--      数据库约束只作为最后一道防线。

CREATE TABLE IF NOT EXISTS students (
    student_id TEXT PRIMARY KEY,
    name       TEXT NOT NULL,
    role       TEXT NOT NULL DEFAULT 'student'
               CHECK (role IN ('student', 'admin'))
);

CREATE TABLE IF NOT EXISTS activities (
    activity_id  INTEGER PRIMARY KEY AUTOINCREMENT,
    title        TEXT    NOT NULL,
    category     TEXT    NOT NULL,
    start_at     TEXT    NOT NULL,
    location     TEXT    NOT NULL,
    capacity     INTEGER NOT NULL CHECK (capacity > 0),
    policy_type  TEXT    NOT NULL CHECK (policy_type IN ('DIRECT', 'APPROVAL')),
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
