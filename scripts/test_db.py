#!/usr/bin/env python3
"""
数据库连通性测试脚本（独立可执行，不依赖项目其他文件）
测试 Docker 中运行的 MySQL / Redis / MongoDB 服务。

MySQL: root / 123456
Redis: 无认证
MongoDB: 无认证
"""

import os
import sys

# 修复 Windows 控制台中文输出乱码
if sys.platform == "win32":
    os.system("chcp 65001 >nul")
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

# ==================== 连接配置 ====================
MYSQL_CONFIG = {
    "host": "localhost",
    "port": 3306,
    "user": "root",
    "password": "123456",
    "database": "meiwei_bot",
}

REDIS_CONFIG = {
    "host": "localhost",
    "port": 6379,
}

MONGODB_CONFIG = {
    "host": "localhost",
    "port": 27017,
}

# 连接超时（毫秒）
TIMEOUT_MS = 3000


def _red(text: str) -> str:
    return f"\033[91m{text}\033[0m"


def _green(text: str) -> str:
    return f"\033[92m{text}\033[0m"


def test_redis() -> bool:
    """测试 Redis 连接与基本操作。"""
    print("\n[Redis 测试开始]")
    try:
        import redis
    except ImportError:
        print(_red("[FAIL] 缺少依赖: redis"))
        print("       请安装: pip install redis")
        return False

    try:
        client = redis.Redis(
            host=REDIS_CONFIG["host"],
            port=REDIS_CONFIG["port"],
            decode_responses=True,
            socket_connect_timeout=TIMEOUT_MS / 1000,
        )

        if not client.ping():
            print(_red("[FAIL] Redis ping 失败"))
            return False
        print(_green("[OK] Redis 连接成功"))

        client.set("db_test_key", "hello redis", ex=10)
        value = client.get("db_test_key")
        print(_green(f"[OK] 读写测试: GET db_test_key = {value}"))

        client.delete("db_test_key")
        print(_green("[OK] Redis 测试数据已清理"))
        return True

    except Exception as e:
        print(_red(f"[FAIL] Redis 连接异常: {e}"))
        return False


def test_mysql() -> bool:
    """测试 MySQL 连接与基本操作。"""
    print("\n[MySQL 测试开始]")
    try:
        import pymysql
    except ImportError:
        print(_red("[FAIL] 缺少依赖: pymysql"))
        print("       请安装: pip install pymysql")
        return False

    connection = None
    try:
        connection = pymysql.connect(
            host=MYSQL_CONFIG["host"],
            port=MYSQL_CONFIG["port"],
            user=MYSQL_CONFIG["user"],
            password=MYSQL_CONFIG["password"],
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor,
            connect_timeout=TIMEOUT_MS / 1000,
        )
        print(_green("[OK] MySQL 服务器连接成功"))

        with connection.cursor() as cursor:
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS {MYSQL_CONFIG['database']}")
            connection.commit()
            print(_green(f"[OK] 数据库 {MYSQL_CONFIG['database']} 已就绪"))

        connection.close()

        connection = pymysql.connect(
            host=MYSQL_CONFIG["host"],
            port=MYSQL_CONFIG["port"],
            user=MYSQL_CONFIG["user"],
            password=MYSQL_CONFIG["password"],
            database=MYSQL_CONFIG["database"],
            charset="utf8mb4",
            cursorclass=pymysql.cursors.DictCursor,
            connect_timeout=TIMEOUT_MS / 1000,
        )

        with connection.cursor() as cursor:
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS connectivity_test (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    message VARCHAR(255) NOT NULL,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            connection.commit()
            print(_green("[OK] 测试表已创建"))

            cursor.execute("INSERT INTO connectivity_test (message) VALUES (%s)", ("hello mysql",))
            connection.commit()
            inserted_id = cursor.lastrowid
            print(_green(f"[OK] 插入数据: id = {inserted_id}"))

            cursor.execute("SELECT * FROM connectivity_test WHERE id = %s", (inserted_id,))
            row = cursor.fetchone()
            print(_green(f"[OK] 查询数据: {row}"))

            cursor.execute("DROP TABLE IF EXISTS connectivity_test")
            connection.commit()
            print(_green("[OK] MySQL 测试数据已清理"))

        return True

    except Exception as e:
        print(_red(f"[FAIL] MySQL 连接异常: {e}"))
        return False

    finally:
        if connection:
            connection.close()


def test_mongodb() -> bool:
    """测试 MongoDB 连接与基本操作。"""
    print("\n[MongoDB 测试开始]")
    try:
        from pymongo import MongoClient
        from pymongo.errors import PyMongoError
    except ImportError:
        print(_red("[FAIL] 缺少依赖: pymongo"))
        print("       请安装: pip install pymongo")
        return False

    client = None
    try:
        client = MongoClient(
            host=MONGODB_CONFIG["host"],
            port=MONGODB_CONFIG["port"],
            serverSelectionTimeoutMS=TIMEOUT_MS,
        )
        # server_info 会触发实际连接（MongoClient 本身是惰性连接）
        info = client.server_info()
        print(_green(f"[OK] MongoDB 连接成功 (version {info.get('version')})"))

        col = client["connectivity_test"]["test_col"]
        inserted_id = col.insert_one({"message": "hello mongodb"}).inserted_id
        print(_green(f"[OK] 插入数据: _id = {inserted_id}"))

        doc = col.find_one({"_id": inserted_id})
        print(_green(f"[OK] 查询数据: {doc}"))

        client.drop_database("connectivity_test")
        print(_green("[OK] MongoDB 测试数据已清理"))
        return True

    except PyMongoError as e:
        print(_red(f"[FAIL] MongoDB 连接异常: {e}"))
        return False

    finally:
        if client:
            client.close()


if __name__ == "__main__":
    print("=" * 50)
    print("数据库服务连通性测试")
    print("=" * 50)

    results = {
        "Redis": test_redis(),
        "MySQL": test_mysql(),
        "MongoDB": test_mongodb(),
    }

    print("\n" + "=" * 50)
    print("测试结果汇总")
    print("=" * 50)
    all_ok = True
    for name, ok in results.items():
        status = _green("通过") if ok else _red("失败")
        print(f"{name:10s} {status}")
        if not ok:
            all_ok = False

    sys.exit(0 if all_ok else 1)
