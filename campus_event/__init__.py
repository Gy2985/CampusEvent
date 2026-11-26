"""CampusEvent 应用工厂。

分层结构（自外向内）：
    web（Flask 蓝图 / 页面）
      └─ services（业务服务：事务边界 + 规则编排）
           ├─ policies（策略模式：变化的报名规则）
           ├─ events + observers（观察者模式：报名事件 → 站内通知）
           └─ repositories（仓储：SQLite 读写）
    domain（实体与业务异常，不依赖 Flask 与数据库）
"""
from __future__ import annotations

import logging
import os

from flask import Flask

from .db import Database
from .events.event_bus import EventBus
from .observers.email_notification_observer import EmailNotificationObserver
from .observers.notification_observer import NotificationObserver
from .policies.implementations import build_default_registry
from .ports.email_sender import MockEmailSender
from .services.activity_service import ActivityService
from .services.registration_service import RegistrationService
from .web import register_blueprints

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def create_app(config: dict | None = None) -> Flask:
    app = Flask(__name__)
    app.config.from_mapping(
        # 云端部署时可用环境变量覆盖：SECRET_KEY 由平台生成，DATABASE_PATH 指向可写目录
        SECRET_KEY=os.environ.get("SECRET_KEY", "campus-event-dev-key"),
        DATABASE=os.environ.get("DATABASE_PATH")
        or os.path.join(BASE_DIR, "data", "campus_event.db"),
        SEED_DEMO=True,
        JSON_AS_ASCII=False,
    )
    if config:
        app.config.update(config)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    db = Database(app.config["DATABASE"])
    db.ensure_ready(seed=bool(app.config.get("SEED_DEMO", True)))

    registry = build_default_registry()
    event_bus = EventBus()
    # 渠道 1：站内消息（baseline-v1 已有）
    event_bus.subscribe(NotificationObserver(db).handle)
    # 渠道 2：模拟邮件（v2 / CR-02；可通过 EMAIL_SENDER 配置替换实现或注入故障）
    email_sender = app.config.get("EMAIL_SENDER") or MockEmailSender()
    event_bus.subscribe(EmailNotificationObserver(db, email_sender).handle)

    app.extensions["db"] = db
    app.extensions["policies"] = registry
    app.extensions["event_bus"] = event_bus
    app.extensions["email_sender"] = email_sender
    app.extensions["registration_service"] = RegistrationService(db, registry, event_bus)
    app.extensions["activity_service"] = ActivityService(db)

    register_blueprints(app)
    return app
