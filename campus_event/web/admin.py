"""管理端页面：活动管理、待审核审批、通知失败留痕查看。"""
from __future__ import annotations

from datetime import timedelta

from flask import Blueprint, flash, redirect, render_template, request, url_for

from ..domain.entities import PolicyType
from ..domain.errors import BusinessError
from ..domain.timeutil import now
from ..repositories import queries
from ..repositories.activity_repository import ActivityRepository
from .context import (
    activity_service,
    admin_required,
    current_user,
    get_db,
    registration_service,
)

bp = Blueprint("admin", __name__, url_prefix="/admin")


@bp.route("/activities")
@admin_required
def activities():
    with get_db().connection() as conn:
        items = queries.activity_overview(conn)
    return render_template("admin_activities.html", activities=items)


@bp.route("/activities/new", methods=["GET", "POST"])
@admin_required
def activity_new():
    if request.method == "POST":
        form = request.form
        try:
            activity_service().create(
                operator_id=current_user().student_id,
                title=form.get("title", ""),
                category=form.get("category", ""),
                start_at=form.get("start_at", ""),
                location=form.get("location", ""),
                capacity=form.get("capacity", ""),
                policy_type=form.get("policy_type", ""),
            )
        except BusinessError as error:
            return render_template(
                "activity_form.html", mode="new", form=form, error=error.message
            )
        flash("活动创建成功。", "success")
        return redirect(url_for("admin.activities"))

    defaults = {"start_at": (now() + timedelta(days=2)).strftime("%Y-%m-%dT%H:%M")}
    return render_template("activity_form.html", mode="new", form=defaults, error=None)


@bp.route("/activities/<int:activity_id>/edit", methods=["GET", "POST"])
@admin_required
def activity_edit(activity_id: int):
    if request.method == "POST":
        form = request.form
        try:
            activity_service().update(
                operator_id=current_user().student_id,
                activity_id=activity_id,
                title=form.get("title", ""),
                category=form.get("category", ""),
                start_at=form.get("start_at", ""),
                location=form.get("location", ""),
                capacity=form.get("capacity", ""),
                policy_type=form.get("policy_type", ""),
            )
        except BusinessError as error:
            with get_db().connection() as conn:
                activity = ActivityRepository(conn).get(activity_id)
            return render_template(
                "activity_form.html",
                mode="edit",
                form=form,
                activity=activity,
                error=error.message,
            )
        flash("活动已更新。", "success")
        return redirect(url_for("admin.activities"))

    with get_db().connection() as conn:
        activity = ActivityRepository(conn).get(activity_id)
    if activity is None:
        flash("活动不存在或已被删除。", "error")
        return redirect(url_for("admin.activities"))

    form = {
        "title": activity.title,
        "category": activity.category,
        "start_at": activity.start_at.replace(" ", "T")[:16],
        "location": activity.location,
        "capacity": activity.capacity,
        "policy_type": activity.policy_type.value,
    }
    return render_template(
        "activity_form.html", mode="edit", form=form, activity=activity, error=None
    )


@bp.route("/activities/<int:activity_id>/delete", methods=["POST"])
@admin_required
def activity_delete(activity_id: int):
    activity_service().delete(current_user().student_id, activity_id)
    flash("活动已删除。", "success")
    return redirect(url_for("admin.activities"))


@bp.route("/reviews")
@admin_required
def reviews():
    with get_db().connection() as conn:
        pending = queries.pending_registration_rows(conn)
        items = queries.activity_overview(conn)
    return render_template("admin_reviews.html", pending=pending, activities=items)


@bp.route("/registrations/<int:registration_id>/approve", methods=["POST"])
@admin_required
def approve(registration_id: int):
    registration = registration_service().approve(
        registration_id, current_user().student_id
    )
    flash(f"已批准报名，当前状态：{registration.status.label}。", "success")
    return redirect(url_for("admin.reviews"))


@bp.route("/registrations/<int:registration_id>/reject", methods=["POST"])
@admin_required
def reject(registration_id: int):
    reason = (request.form.get("reason") or "").strip()
    registration = registration_service().reject(
        registration_id, current_user().student_id, reason
    )
    flash(f"已拒绝报名，当前状态：{registration.status.label}。", "success")
    return redirect(url_for("admin.reviews"))


@bp.route("/failures")
@admin_required
def failures():
    with get_db().connection() as conn:
        rows = queries.failure_rows(conn)
    return render_template("admin_failures.html", rows=rows)


__all__ = ["bp", "PolicyType"]
