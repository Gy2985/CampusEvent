"""时间处理工具：全系统统一使用 "YYYY-MM-DD HH:MM:SS" 文本存储。"""
from __future__ import annotations

from datetime import datetime

DT_FORMAT = "%Y-%m-%d %H:%M:%S"
MINUTE_FORMAT = "%Y-%m-%d %H:%M"


def now() -> datetime:
    """返回当前本地时间（秒级精度）。"""
    return datetime.now().replace(microsecond=0)


def format_dt(value: datetime | None) -> str | None:
    if value is None:
        return None
    return value.strftime(DT_FORMAT)


def parse_dt(text: str | None) -> datetime | None:
    """解析数据库中的时间文本，兼容 'YYYY-MM-DD HH:MM' 与 ISO 形式。"""
    if not text:
        return None
    text = text.strip()
    for fmt in (DT_FORMAT, MINUTE_FORMAT, "%Y-%m-%dT%H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    raise ValueError(f"无法识别的时间格式：{text}")


def parse_user_input(text: str) -> datetime:
    """解析网页表单（datetime-local 控件）提交的时间。"""
    text = (text or "").strip()
    if not text:
        raise ValueError("时间不能为空")
    return parse_dt(text.replace("T", " "))


def display(text: str | None) -> str:
    """用于页面展示：去掉秒，保留到分钟。"""
    dt = parse_dt(text)
    return dt.strftime(MINUTE_FORMAT) if dt else ""
