"""数据库初始化脚本：清空并重建表结构与演示数据。

用法：
    python init_db.py            # 重建 data/campus_event.db 并写入演示数据
    python init_db.py --no-seed  # 只建表，不写演示数据
"""
from __future__ import annotations

import argparse
import os

from campus_event import BASE_DIR
from campus_event.db import Database

DB_PATH = os.path.join(BASE_DIR, "data", "campus_event.db")


def main() -> None:
    parser = argparse.ArgumentParser(description="初始化 CampusEvent 数据库")
    parser.add_argument("--no-seed", action="store_true", help="不写入演示数据")
    parser.add_argument("--db", default=DB_PATH, help="数据库文件路径")
    args = parser.parse_args()

    db = Database(args.db)
    db.initialize(seed=not args.no_seed)
    print(f"数据库已初始化：{db.path}")
    if not args.no_seed:
        print("演示账号：S001/S002/S003（学生），A001（管理员）")


if __name__ == "__main__":
    main()
