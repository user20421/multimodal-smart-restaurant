#!/usr/bin/env python3
"""
生成 MySQL 初始化 SQL 脚本

从 backend/app/core/seed_data.py 读取内置菜单分类与菜品数据，
生成 rawfiles/sql/init.sql，包含建库、建表、初始菜单数据和管理员账号。

使用方法：
  python rawfiles/sql/generate_init_sql.py
"""

import os
import sys
from pathlib import Path

# 项目根目录
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from app.core.seed_data import get_menu_items, get_menu_categories

OUTPUT_FILE = Path(__file__).resolve().parent / "init.sql"

# 数据库配置（与 backend/.env.example 保持一致）
DATABASE_NAME = "meiwei_bot"
ADMIN_USERNAME = "root"
ADMIN_PASSWORD = "123456"
ADMIN_PHONE = "13800138000"


def _try_bcrypt(password: str) -> str:
    """尝试生成 bcrypt 密码哈希；失败则返回明文占位符。"""
    try:
        import bcrypt
        hashed = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt())
        return hashed.decode("utf-8")
    except ImportError:
        print("警告：未安装 bcrypt，SQL 中将使用明文占位符，请手动替换为真实哈希。", file=sys.stderr)
        return f"__bcrypt_hash_of_{password}__"


def escape_sql(value) -> str:
    """转义 SQL 字符串值。"""
    if value is None:
        return "NULL"
    if isinstance(value, (int, float)):
        return str(value)
    s = str(value).replace("\\", "\\\\").replace("'", "\\'")
    return f"'{s}'"


def generate_sql() -> str:
    categories = get_menu_categories()
    items = get_menu_items()
    admin_password_hash = _try_bcrypt(ADMIN_PASSWORD)

    lines = [
        "-- ============================================",
        "-- 美味餐厅 · MySQL 初始化脚本",
        "-- 生成时间: 由 generate_init_sql.py 自动生成",
        "-- 说明: 包含建库、建表、初始菜单数据和管理员账号",
        "-- ============================================",
        "",
        f"DROP DATABASE IF EXISTS `{DATABASE_NAME}`;",
        "",
        f"CREATE DATABASE `{DATABASE_NAME}`",
        "    CHARACTER SET utf8mb4",
        "    COLLATE utf8mb4_unicode_ci;",
        "",
        f"USE `{DATABASE_NAME}`;",
        "",
        "-- 用户表",
        "CREATE TABLE IF NOT EXISTS `users` (",
        "    `id` INT AUTO_INCREMENT PRIMARY KEY,",
        "    `username` VARCHAR(50) NOT NULL UNIQUE COMMENT '用户名',",
        "    `password` VARCHAR(200) NOT NULL COMMENT '密码bcrypt哈希',",
        "    `role` VARCHAR(20) DEFAULT 'customer' COMMENT '角色: customer/admin',",
        "    `phone` VARCHAR(20) DEFAULT NULL COMMENT '手机号',",
        "    `gender` VARCHAR(10) DEFAULT NULL COMMENT '性别: male/female',",
        "    `birth_date` DATE DEFAULT NULL COMMENT '出生日期',",
        "    `need_change_password` TINYINT(1) DEFAULT 0 COMMENT '是否需要强制修改密码',",
        "    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',",
        "    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间'",
        ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;",
        "",
        "-- 菜单分类表",
        "CREATE TABLE IF NOT EXISTS `menu_categories` (",
        "    `id` INT AUTO_INCREMENT PRIMARY KEY,",
        "    `name` VARCHAR(50) NOT NULL UNIQUE COMMENT '分类名称',",
        "    `sort_order` INT DEFAULT 0 COMMENT '排序',",
        "    `description` TEXT COMMENT '分类描述',",
        "    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP",
        ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;",
        "",
        "-- 菜单菜品表",
        "CREATE TABLE IF NOT EXISTS `menu_items` (",
        "    `id` INT AUTO_INCREMENT PRIMARY KEY,",
        "    `name` VARCHAR(100) NOT NULL COMMENT '菜品名称',",
        "    `description` TEXT COMMENT '菜品描述',",
        "    `price` FLOAT NOT NULL COMMENT '价格（元）',",
        "    `spicy_level` INT DEFAULT 0 COMMENT '辣度 0-5',",
        "    `category` VARCHAR(50) NOT NULL COMMENT '分类名称',",
        "    `tags` VARCHAR(300) COMMENT '标签，逗号分隔',",
        "    `stock` INT DEFAULT 100 COMMENT '库存数量',",
        "    `is_recommended` INT DEFAULT 0 COMMENT '是否推荐 0/1',",
        "    `sales_count` INT DEFAULT 0 COMMENT '销量',",
        "    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,",
        "    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,",
        "    INDEX `idx_menu_item_name` (`name`),",
        "    INDEX `idx_menu_item_category` (`category`),",
        "    INDEX `idx_menu_item_sales` (`sales_count`)",
        ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;",
        "",
        "-- 订单表",
        "CREATE TABLE IF NOT EXISTS `orders` (",
        "    `id` INT AUTO_INCREMENT PRIMARY KEY,",
        "    `user_id` INT NOT NULL COMMENT '用户ID',",
        "    `status` VARCHAR(20) DEFAULT 'confirmed' COMMENT '状态: pending/confirmed/completed/cancelled',",
        "    `total_price` FLOAT NOT NULL DEFAULT 0 COMMENT '总价',",
        "    `remark` TEXT COMMENT '订单备注',",
        "    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP COMMENT '创建时间',",
        "    `updated_at` DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP COMMENT '更新时间',",
        "    INDEX `idx_order_user_created` (`user_id`, `created_at`),",
        "    INDEX `idx_order_status` (`status`),",
        "    CONSTRAINT `fk_orders_user_id` FOREIGN KEY (`user_id`) REFERENCES `users` (`id`) ON DELETE CASCADE",
        ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;",
        "",
        "-- 订单明细表",
        "CREATE TABLE IF NOT EXISTS `order_items` (",
        "    `id` INT AUTO_INCREMENT PRIMARY KEY,",
        "    `order_id` INT NOT NULL COMMENT '订单ID',",
        "    `menu_item_id` INT NOT NULL COMMENT '菜品ID',",
        "    `quantity` INT NOT NULL DEFAULT 1 COMMENT '数量',",
        "    `unit_price` FLOAT NOT NULL COMMENT '单价',",
        "    `created_at` DATETIME DEFAULT CURRENT_TIMESTAMP,",
        "    INDEX `idx_order_item_order` (`order_id`),",
        "    CONSTRAINT `fk_order_items_order_id` FOREIGN KEY (`order_id`) REFERENCES `orders` (`id`) ON DELETE CASCADE,",
        "    CONSTRAINT `fk_order_items_menu_item_id` FOREIGN KEY (`menu_item_id`) REFERENCES `menu_items` (`id`)",
        ") ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;",
        "",
        "-- ============================================",
        "-- 初始数据",
        "-- ============================================",
        "",
        "-- 管理员账号",
        "INSERT IGNORE INTO `users` (`username`, `password`, `role`, `phone`, `gender`, `birth_date`, `need_change_password`) VALUES",
        f"    ({escape_sql(ADMIN_USERNAME)}, {escape_sql(admin_password_hash)}, 'admin', {escape_sql(ADMIN_PHONE)}, NULL, NULL, 1);",
        "",
        "-- 菜单分类",
        "INSERT IGNORE INTO `menu_categories` (`name`, `sort_order`, `description`) VALUES",
    ]

    cat_values = []
    for cat in categories:
        cat_values.append(
            f"    ({escape_sql(cat['name'])}, {cat['sort_order']}, {escape_sql(cat['description'] or None)})"
        )
    lines.append(",\n".join(cat_values) + ";")

    lines.append("")
    lines.append("-- 菜单菜品")
    lines.append("INSERT IGNORE INTO `menu_items` (`name`, `description`, `price`, `spicy_level`, `category`, `tags`, `stock`, `is_recommended`) VALUES")

    item_values = []
    for item in items:
        item_values.append(
            f"    ({escape_sql(item['name'])}, {escape_sql(item['description'] or None)}, "
            f"{item['price']}, {item['spicy_level']}, {escape_sql(item['category'])}, "
            f"{escape_sql(item['tags'] or None)}, {item['stock']}, {item['is_recommended']})"
        )
    lines.append(",\n".join(item_values) + ";")

    lines.append("")
    lines.append("-- 数据汇总")
    lines.append(f"-- 分类数量: {len(categories)}")
    lines.append(f"-- 菜品数量: {len(items)}")

    return "\n".join(lines) + "\n"


def main():
    sql = generate_sql()
    OUTPUT_FILE.write_text(sql, encoding="utf-8")
    print(f"已生成初始化 SQL 文件: {OUTPUT_FILE}")
    print(f"  数据库: {DATABASE_NAME}")
    print(f"  分类数: {len(get_menu_categories())}")
    print(f"  菜品数: {len(get_menu_items())}")
    print(f"  管理员账号: {ADMIN_USERNAME} / {ADMIN_PASSWORD}")


if __name__ == "__main__":
    main()
