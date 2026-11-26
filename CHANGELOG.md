# 变更记录（CHANGELOG）

格式参考 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，版本号对应 Git 标签。

## [v2] - 2026-11-26 · `change-v2`

对应教师材料中的两张需求变更单（在 `baseline-v1` 验收后发布）。

### 新增（CR-01 年级限定直接报名）

- `Student.grade`（1–4，管理员为空），登录页与导航栏显示年级
- `PolicyType.GRADE_LIMITED` 与 `GradeLimitedDirectPolicy`：仅 `grade ∈ {2,3}` 可报名
- `GradeRestrictedError`：资格不符时明确提示，事务回滚、不落任何报名记录
- 演示活动"职业规划工作坊（大二大三专场）"

### 新增（CR-02 模拟邮件通知）

- `ports/email_sender.py`：`EmailSender` 端口 + `MockEmailSender`（可注入故障）
- `observers/email_notification_observer.py`：订阅事件、独立于站内通知
- `email_outbox` 表 + `EmailRepository`：先占位（QUEUED）再完结（SENT/FAILED）
- 管理端 `/admin/emails` 页面：查看收件人、主题、状态与失败错误

### 变更

- `activities.policy_type` 的 CHECK 约束放宽到三值（SQLite 需重建表，已提供幂等迁移 `Database.upgrade()`）
- 老库升级时为演示账号回填年级（仅当 `grade IS NULL`）

### 测试

- 36 项基调用例全部保持通过；新增 15 项变更/迁移/界面用例，合计 **51 passed**

## [v1] - 2026-11-25 · `baseline-v1`

- 实验二初始版本：P2-F01 ~ P2-F08（活动管理、浏览筛选、报名取消、两类报名策略、审批、四种状态、站内通知、名额统计）
- 策略模式（报名规则）+ 观察者模式（站内通知）；36 项 pytest 全通过；UML 与实验文档齐全
- Gitee / GitHub 双仓库，Render 免费实例线上可访问
