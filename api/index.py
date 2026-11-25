"""Vercel Serverless 入口：把 Flask 应用暴露成 WSGI 函数。

Vercel 的 Python 运行时只认 ``api/`` 目录下的函数文件，并且要求模块里存在
名为 ``app`` 的 WSGI 可调用对象。平台文件系统只读，因此数据库必须落到
``/tmp``（免费实例为临时盘，冷启动会回到初始演示数据，属预期行为）。
"""
from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

os.environ.setdefault("DATABASE_PATH", "/tmp/campus_event.db")

from app import app  # noqa: E402,F401  Vercel 用这个名字识别 WSGI 应用
