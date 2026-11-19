"""登录（固定演示账号，无注册/无密码，符合附录 B.1 的范围约定）。"""
from __future__ import annotations

from flask import Blueprint, redirect, render_template, request, session, url_for

from ..repositories.student_repository import StudentRepository
from .context import get_db

bp = Blueprint("auth", __name__)


@bp.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        user_id = (request.form.get("user_id") or "").strip()
        with get_db().connection() as conn:
            user = StudentRepository(conn).get(user_id)
        if user is None:
            return render_template("login.html", users=_users(), error="账号不存在，请重新选择。")
        session.clear()
        session["user_id"] = user.student_id
        session["user_name"] = user.name
        return redirect(url_for("admin.activities") if user.is_admin else url_for("student.activities"))

    return render_template("login.html", users=_users(), error=None)


@bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("auth.login"))


def _users():
    with get_db().connection() as conn:
        return StudentRepository(conn).list_all()
