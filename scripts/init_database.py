#!/usr/bin/env python3
"""
数据库初始化脚本

执行 rawfiles/sql/init.sql，完成：
- 删除现有数据库 meiwei_bot
- 重新创建数据库和表
- 插入初始菜单数据和管理员账号

警告：此操作会清空所有业务数据，请谨慎使用！
"""
import argparse
import sys
from pathlib import Path

import pymysql


ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_SQL_FILE = ROOT_DIR / "rawfiles" / "sql" / "init.sql"


def run_init_sql(host: str, port: int, user: str, password: str, sql_file: Path) -> None:
    """连接 MySQL 并执行初始化 SQL 脚本。"""
    if not sql_file.exists():
        print(f"[错误] SQL 文件不存在: {sql_file}", file=sys.stderr)
        sys.exit(1)

    print(f"[信息] 正在读取 SQL 文件: {sql_file}")
    with open(sql_file, "r", encoding="utf-8") as f:
        sql_content = f.read()

    print(f"[信息] 正在连接 MySQL {host}:{port} ...")
    conn = pymysql.connect(
        host=host,
        port=port,
        user=user,
        password=password,
        charset="utf8mb4",
        autocommit=False,
    )

    try:
        with conn.cursor() as cursor:
            # 按分号拆分语句并逐条执行
            statements = [s.strip() for s in sql_content.split(";") if s.strip()]
            total = len(statements)
            for idx, stmt in enumerate(statements, start=1):
                cursor.execute(stmt)
                # 简单输出进度
                if idx % 10 == 0 or idx == total:
                    print(f"[进度] 已执行 {idx}/{total} 条 SQL 语句")
        conn.commit()
        print("[成功] 数据库初始化完成")
    except Exception as e:
        conn.rollback()
        print(f"[错误] 初始化失败: {e}", file=sys.stderr)
        sys.exit(1)
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(
        description="删除并重建美味餐厅数据库（执行 rawfiles/sql/init.sql）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  python scripts/init_database.py
  python scripts/init_database.py --host 127.0.0.1 --port 3306 --user root --password 123456
""",
    )
    parser.add_argument("--host", default="localhost", help="MySQL 主机地址 (默认: localhost)")
    parser.add_argument("--port", type=int, default=3306, help="MySQL 端口 (默认: 3306)")
    parser.add_argument("--user", default="root", help="MySQL 用户名 (默认: root)")
    parser.add_argument("--password", default="123456", help="MySQL 密码 (默认: 123456)")
    parser.add_argument(
        "--sql-file",
        type=Path,
        default=DEFAULT_SQL_FILE,
        help=f"初始化 SQL 文件路径 (默认: {DEFAULT_SQL_FILE})",
    )

    args = parser.parse_args()

    print("=" * 50)
    print("警告：此操作会删除并重建数据库，所有业务数据将丢失！")
    print("=" * 50)
    run_init_sql(
        host=args.host,
        port=args.port,
        user=args.user,
        password=args.password,
        sql_file=args.sql_file,
    )


if __name__ == "__main__":
    main()
