"""
FastAPI 应用入口
"""
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse

from app.core.exceptions import AppException
from app.core.database import init_db, AsyncSessionLocal
from app.core.logging_config import setup_logging, get_logger
from app.core.config import settings
from app.api.v1 import auth, menu, order, admin, system
from app.services.init_service import initialize_system

# 导入所有模型，确保 Base.metadata 包含所有表
import app.models  # noqa: F401

# 初始化日志
setup_logging()
logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    应用生命周期管理
    启动时：建表 + 初始化数据
    """
    app.state.startup_time = datetime.now(timezone.utc).isoformat()

    # JWT 密钥安全检查
    if settings.jwt_secret_key in ("your-secret-key-change-in-production", ""):
        logger.warning("JWT_SECRET_KEY 使用的是默认弱密钥，生产环境请务必修改")

    # 创建数据库表
    await init_db()

    # 初始化数据
    async with AsyncSessionLocal() as db:
        await initialize_system(db)

    yield

    # 无其他外部资源需要关闭


app = FastAPI(
    title=settings.app_name,
    description="基于 FastAPI 的美味餐厅点餐系统",
    version=settings.version,
    lifespan=lifespan,
)


@app.exception_handler(AppException)
async def app_exception_handler(request: Request, exc: AppException):
    """统一业务异常处理"""
    logger.warning(f"[Exception] {exc.status_code}: {exc.message}")
    return JSONResponse(
        status_code=exc.status_code,
        content={"detail": exc.message},
    )

# CORS 配置：开发模式允许所有来源但不允许携带凭证，生产模式从配置读取
is_prod = settings.serve_static
if is_prod:
    # 生产环境建议配置具体域名
    cors_origins = [o.strip() for o in settings.cors_origins.split(",") if o.strip()]
    allow_creds = settings.cors_allow_credentials
else:
    cors_origins = ["*"]
    allow_creds = False

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=allow_creds,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(auth.router, prefix="/api/v1", tags=["认证"])
app.include_router(menu.router, prefix="/api/v1", tags=["菜单"])
app.include_router(order.router, prefix="/api/v1", tags=["订单"])
app.include_router(admin.router, prefix="/api/v1", tags=["商家管理"])
app.include_router(system.router, prefix="/api/v1", tags=["系统"])


@app.get("/health")
async def health_check():
    return {"status": "ok", "app": settings.app_name}


# 挂载应用静态资源目录（当前无内容，保留挂载以备后用）
static_files_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), settings.static_dir)
os.makedirs(static_files_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_files_dir), name="static")

# 生产模式：托管前端静态文件（必须在 API 路由之后挂载，保证 API 优先）
if is_prod:
    dist_dir = settings.frontend_dist_dir
    if os.path.isdir(dist_dir):
        # 挂载静态文件目录；html=True 表示对于不存在的路径自动返回 index.html
        app.mount("/", StaticFiles(directory=dist_dir, html=True), name="frontend")
        logger.info(f"[生产模式] 已挂载前端静态文件目录: {dist_dir}")
    else:
        logger.warning(f"[生产模式] 前端静态文件目录不存在: {dist_dir}")
else:
    @app.get("/")
    async def root():
        """开发模式 API 根路径信息"""
        return {"message": "欢迎使用美味餐厅 API", "docs": "/docs", "version": settings.version}
