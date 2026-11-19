"""Web 层公共设施：服务定位、登录态、装饰器与错误兜底。"""
from __future__ import annotations

from functools import wraps

from flask import current_app, flash, redirect, g, request, session, url_for

from ..domain.entities import Student
from ..domain.errors import BusinessError
from ..repositories.student_repository import StudentRepository
from ..services.activity_service import ActivityService
from ..services.registration_service import RegistrationService


def get_db():
    return current_app.extensions["db"]


def registration_service() -> RegistrationService:
    return current_app.extensions["registration_service"]


def activity_service() -> ActivityService:
    return current_app.extensions["activity_service"]


def current_user() -> Student | None:
    """从 session 读取演示账号；未登录返回 None。"""
    if "user" in g:
        return g.user
    user_id = session.get("user_id")
    user = None
    if user_id:
        with get_db().connection() as conn:
            user = StudentRepository(conn).get(user_id)
    g.user = user
    return user


def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if current_user() is None:
            flash("请先选择演示账号登录。", "error")
            return redirect(url_for("auth.login"))
        return view(*args, **kwargs)

    return wrapper


def admin_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        user = current_user()
        if user is None:
            flash("请先选择演示账号登录。", "error")
            return redirect(url_for("auth.login"))
        if not user.is_admin:
            flash("该功能仅管理员可用。", "error")
            return redirect(url_for("student.activities"))
        return view(*args, **kwargs)

    return wrapper


def register_error_handlers(app) -> None:
    """把业务异常统一转换为页面提示，避免出现 500 白屏。"""

    @app.errorhandler(BusinessError)
    def handle_business_error(error: BusinessError):
        flash(error.message, "error")
        return redirect(request.referrer or url_for("student.activities"))

    @app.errorhandler(404)
    def handle_404(error):
        flash("页面不存在。", "error")
        return redirect(url_for("student.activities"))
