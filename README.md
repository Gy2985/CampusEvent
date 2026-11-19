# CampusEvent 校园活动报名与管理系统

> 《软件工程》课程实验二（项目代号 **CampusEvent**）
> 设计方式：学生主导设计（UML + 模式决策）→ AI 辅助实现 → 自动化测试验收
> 核心关注：**需求变化时，设计是否让修改更便宜**

---

## 1. 项目范围

初始版本对应指导书 3.2 节 P2-F01 ~ P2-F08：

| 编号 | 功能模块 | 实现情况 | 主要代码位置 |
| --- | --- | --- | --- |
| P2-F01 | 活动管理（增删改） | 已实现 | `campus_event/services/activity_service.py`、`web/admin.py` |
| P2-F02 | 活动查看（列表 + 详情 + 按名称筛选） | 已实现 | `web/student.py`、`repositories/queries.py` |
| P2-F03 | 报名 / 取消，禁止重复有效报名 | 已实现 | `services/registration_service.py` |
| P2-F04 | 报名策略：直接报名 / 审核型 | 已实现（策略模式） | `policies/` |
| P2-F05 | 审批：批准 / 拒绝，批准时复查名额 | 已实现 | `RegistrationService.approve/reject` |
| P2-F06 | 状态管理：待审核 / 已通过 / 已拒绝 / 已取消 | 已实现 | `domain/entities.py` + 服务层状态校验 |
| P2-F07 | 站内通知（报名结果、审核结果） | 已实现（观察者模式） | `events/`、`observers/notification_observer.py` |
| P2-F08 | 统计：已通过数、待审核数、剩余名额 | 已实现 | `repositories/queries.py`、`admin/reviews` 页面 |

明确不做：注册登录与密码体系（使用固定演示账号）、消息队列、多节点部署、软删除。

---

## 2. 快速开始（从零运行）

### 2.1 环境要求

- Python 3.11 及以上（本机实测：`D:\python` 中的 Python 3.13.9，Anaconda 自带）
- 无需数据库服务：使用文件型 SQLite，首次启动自动建库

### 2.2 安装依赖（Windows PowerShell）

```powershell
cd D:\CampusEvent
D:\python\python.exe -m venv .venv          # 虚拟环境落在 D 盘，不占用 C 盘
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 2.3 初始化数据库（可选）

```powershell
.\.venv\Scripts\python.exe init_db.py
```

> 首次启动时若 `data/campus_event.db` 不存在，应用会自动建表并写入演示数据，可跳过本步。
> 想清空数据重新演示，再次运行 `init_db.py` 即可。

### 2.4 启动

```powershell
.\.venv\Scripts\python.exe app.py
```

浏览器访问 <http://127.0.0.1:5000> 。

### 2.5 演示账号（固定账号，无密码）

| 账号 | 姓名 | 角色 |
| --- | --- | --- |
| S001 | 张三（学生A） | 学生 |
| S002 | 李四（学生B） | 学生 |
| S003 | 王五（学生C） | 学生 |
| A001 | 赵老师（管理员） | 管理员 |

### 2.6 运行自动化测试

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

当前结果：**36 passed**（C1–C10 核心验收用例 + X1–X13 边界用例）。

---

## 3. 目录结构

```
CampusEvent/
├─ app.py                      # 开发服务器入口
├─ init_db.py                  # 建库 + 演示数据
├─ requirements.txt
├─ AI_DEV_LOG.md               # AI 协作过程记录
├─ campus_event/
│  ├─ __init__.py              # 应用工厂：装配策略注册表、事件总线、观察者
│  ├─ db.py                    # SQLite 连接与显式事务
│  ├─ schema.sql               # 表结构与约束
│  ├─ domain/                  # 实体、状态枚举、业务异常、时间工具
│  ├─ policies/                # 策略模式：报名规则抽象与两种实现 + 注册表
│  ├─ events/                  # 领域事件 + 进程内事件总线（Subject）
│  ├─ observers/               # 站内通知观察者（Observer）
│  ├─ repositories/            # 仓储（SQLite 读写）与页面读模型
│  ├─ services/                # 业务服务：事务边界与规则编排
│  ├─ web/                     # Flask 蓝图：auth / student / admin
│  ├─ templates/               # 页面模板
│  └─ static/style.css
├─ tests/                      # pytest：C1–C10 + 边界用例
├─ docs/                       # 需求分析、UML 图、设计决策、回归测试表、实验报告
└─ data/campus_event.db        # 运行后生成
```

---

## 4. 设计要点（详见 `docs/06-设计模式决策报告.md`）

**分层**：`web → services → (policies | events+observers | repositories) → domain`。
`domain` 不依赖 Flask 与数据库，可被单元测试直接驱动。

**策略模式**：`RegistrationPolicy`（抽象）→ `DirectRegistrationPolicy` / `ApprovalRegistrationPolicy`。
`RegistrationService` 依赖抽象，通过 `PolicyRegistry` 按活动上的 `policy_type` 取实现，主流程中**没有** `if 活动类型 == ...`。

**名额检查放在哪**：属于**公共规则**，由 `RegistrationService` 统一执行；策略只用 `requires_immediate_capacity_check` 声明是否需要“提交即校验”。
- 直接报名：提交即校验，满员拒绝；
- 审核型报名：提交不校验（待审核不占名额，允许排队），**批准时**再校验，满员则批准失败。

**观察者模式**：报名/审批产生 `RegistrationEvent` → `EventBus` 发布 → `NotificationObserver` 写站内消息。
- 事件在**事务提交之后**发布：通知失败不影响已提交的报名；
- 失败写入 `notification_failures` 表 + 日志，可人工补发；
- `messages.dedupe_key` 唯一索引 + `INSERT OR IGNORE` 保证同一事件**只通知一次**。

**数据一致性**：报名、审批都在 `BEGIN IMMEDIATE` 显式事务中完成；数据库层再用
`UNIQUE INDEX ... WHERE status IN ('PENDING','APPROVED')` 兜底防止并发重复报名。

---

## 5. 已知限制

1. 需求变更（CR）尚未发布，`change-v2` 分支与变更实现按课程安排在收到 CR 后完成，
   影响分析模板见 `docs/07-需求变更影响分析.md`。
2. 尚未部署到云服务器（实验要求必须部署），本地已验证可运行。
3. 未做多用户并发压测；SQLite 为单机写锁模型，适合本实验规模。
4. 无密码与权限体系，仅按附录 B.1 的固定演示账号区分角色。

---

## 6. 版本管理

仓库已建立两个可追踪版本的起点：

| 标签 | 含义 |
| --- | --- |
| `baseline-v1` | 初始验收版本（本 README 描述的功能） |
| `change-v2` | 收到 CR 后在 `feature/cr` 分支上完成，打标签后合入 |

提交信息采用 `feat/fix/test/docs` 前缀，便于回溯“哪次修改对应哪条需求”。

---

## 7. 素材引用

UML 图与实验报告均在 `docs/` 下，图示源文件（PlantUML `.puml`）与导出的 PNG 一并提交，
便于评审学生核对设计与代码是否一致。
