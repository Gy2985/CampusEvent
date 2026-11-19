"""学生端页面：浏览活动、报名、取消、我的报名、站内消息。"""
from __future__ import annotations

from flask import Blueprint, flash, redirect, render_template, request, url_for

from ..domain.errors import NotFoundError
from ..repositories import queries
from .context import current_user, get_db, login_required, registration_service

bp = Blueprint("student", __name__)


@bp.route("/")
def index():
    return redirect(url_for("student.activities"))


@bp.route("/activities")
@login_required
def activities():
    keyword = (request.args.get("q") or "").strip()
    user = current_user()
    with get_db().connection() as conn:
        items = queries.activity_overview(
            conn, search=keyword or None, student_id=user.student_id
        )
    return render_template("activities.html", activities=items, keyword=keyword)


@bp.route("/activities/<int:activity_id>")
@login_required
def activity_detail(activity_id: int):
    user = current_user()
    with get_db().connection() as conn:
        activity = queries.activity_detail(conn, activity_id, user.student_id)
        registrations = (
            queries.activity_registration_rows(conn, activity_id) if user.is_admin else []
        )
    if activity is None:
        raise NotFoundError("活动不存在或已被删除。")
    return render_template(
        "activity_detail.html", activity=activity, registrations=registrations
    )


@bp.route("/activities/<int:activity_id>/register", methods=["POST"])
@login_required
def register(activity_id: int):
    user = current_user()
    registration = registration_service().register(activity_id, user.student_id)
    flash(f"报名已提交，当前状态：{registration.status.label}。", "success")
    return redirect(url_for("student.activity_detail", activity_id=activity_id))


@bp.route("/registrations/<int:registration_id>/cancel", methods=["POST"])
@login_required
def cancel(registration_id: int):
    user = current_user()
    registration = registration_service().cancel(registration_id, user.student_id)
    flash("报名已取消，统计已同步更新。", "success")
    return redirect(url_for("student.my_registrations"))


@bp.route("/my/registrations")
@login_required
def my_registrations():
    user = current_user()
    with get_db().connection() as conn:
        rows = queries.student_registration_rows(conn, user.student_id)
    return render_template("my_registrations.html", rows=rows)


@bp.route("/messages")
@login_required
def messages():
    user = current_user()
    with get_db().connection() as conn:
        rows = queries.message_rows(conn, user.student_id)
    return render_template("messages.html", rows=rows)


@bp.route("/messages/read", methods=["POST"])
@login_required
def mark_messages_read():
    user = current_user()
    from ..repositories.message_repository import MessageRepository

    with get_db().transaction() as conn:
        count = MessageRepository(conn).mark_read(user.student_id)
    flash(f"已把 {count} 条消息标记为已读。", "success")
    return redirect(url_for("student.messages"))
