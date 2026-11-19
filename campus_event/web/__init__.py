"""注册所有蓝图与上下文处理器。"""
from __future__ import annotations

from flask import Flask

from ..repositories.message_repository import MessageRepository
from . import admin, auth, student
from .context import current_user, get_db, register_error_handlers


def register_blueprints(app: Flask) -> None:
    app.register_blueprint(auth.bp)
    app.register_blueprint(student.bp)
    app.register_blueprint(admin.bp)
    register_error_handlers(app)

    @app.context_processor
    def inject_globals():
        user = current_user()
        unread = 0
        if user is not None:
            with get_db().connection() as conn:
                unread = MessageRepository(conn).unread_count(user.student_id)
        return {"current_user": user, "unread_count": unread}
