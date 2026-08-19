"""
项目核心配置
使用 Pydantic Settings 读取配置，优先级：.env 文件 > 环境变量 > 默认值

IS_SERVER=false（开发模式）：MySQL/Redis 使用代码内置的本地默认配置（root/123456、无密码、默认端口），
                          .env 中的 DATABASE_URL/REDIS_URL 不生效。
IS_SERVER=true（部署模式）：  使用 .env 中的 DATABASE_URL/REDIS_URL（含用户名/密码/端口）。
"""
from functools import lru_cache

from pydantic import model_validator
from pydantic_settings import BaseSettings, PydanticBaseSettingsSource

# 开发模式内置的本地默认连接（IS_SERVER=false 时强制生效）
_DEV_DATABASE_URL = "mysql+aiomysql://root:123456@localhost:3306/meiwei_bot"
_DEV_REDIS_URL = "redis://localhost:6379/0"


class Settings(BaseSettings):
    # 是否部署模式（false=开发，使用内置本地数据库配置；true=部署，使用 .env 连接信息）
    is_server: bool = False

    # 应用配置
    app_name: str = "美味餐厅"
    debug: bool = False
    version: str = "3.0.0"

    # 数据库配置 (MySQL)，仅部署模式生效；开发模式强制使用 _DEV_DATABASE_URL
    database_url: str = _DEV_DATABASE_URL

    # JWT 配置
    jwt_secret_key: str = "your-secret-key-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_hours: int = 24

    # Redis 配置，仅部署模式生效；开发模式强制使用 _DEV_REDIS_URL
    redis_url: str = _DEV_REDIS_URL

    # 日志配置
    log_level: str = "INFO"

    # 静态资源目录（保留挂载，相对于 backend/ 目录）
    static_dir: str = "static"

    # 生产模式：托管前端静态文件
    serve_static: bool = False
    frontend_dist_dir: str = "../frontend/dist"

    # CORS 配置（仅生产模式生效；开发模式放行全部来源）
    cors_origins: str = "*"
    cors_allow_credentials: bool = False

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }

    @model_validator(mode="after")
    def _apply_mode_defaults(self) -> "Settings":
        # 开发模式：数据库连接强制使用内置本地默认配置，忽略 .env 中的连接信息
        if not self.is_server:
            self.database_url = _DEV_DATABASE_URL
            self.redis_url = _DEV_REDIS_URL
        return self

    @classmethod
    def settings_customise_sources(
        cls,
        settings_cls: type[BaseSettings],
        init_settings: PydanticBaseSettingsSource,
        env_settings: PydanticBaseSettingsSource,
        dotenv_settings: PydanticBaseSettingsSource,
        file_secret_settings: PydanticBaseSettingsSource,
    ) -> tuple[PydanticBaseSettingsSource, ...]:
        # .env 文件优先于系统环境变量（.env 中没有的键才回退到环境变量）
        return (init_settings, dotenv_settings, env_settings, file_secret_settings)


@lru_cache()
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
