"""
项目核心配置
使用 Pydantic Settings 从环境变量和 .env 文件读取配置
"""
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    # 应用配置
    app_name: str = "美味餐厅"
    debug: bool = False
    version: str = "3.0.0"

    # 数据库配置 (MySQL)
    database_url: str = "mysql+aiomysql://root:123456@localhost:3306/meiwei_bot"

    # JWT 配置
    jwt_secret_key: str = "your-secret-key-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_hours: int = 24

    # Redis 配置
    redis_url: str = "redis://localhost:6379/0"

    # 日志配置
    log_level: str = "INFO"

    # 静态资源目录
    static_dir: str = "static"

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
