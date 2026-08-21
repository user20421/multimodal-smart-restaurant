"""
使用 TestClient 的 API 单元测试
无需启动独立服务器
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import declarative_base

from app.main import app
from app.core.database import get_db, Base
from app.services.captcha_service import _memory_cache, CAPTCHA_KEY_PREFIX

# 使用 SQLite 内存数据库做测试
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestSessionLocal = async_sessionmaker(test_engine, class_=AsyncSession, expire_on_commit=False)


async def override_get_db():
    async with TestSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)


@pytest.fixture(scope="session", autouse=True)
def setup_database():
    """创建测试数据库表"""
    import asyncio
    asyncio.run(_init_db())
    yield
    asyncio.run(_close_db())


async def _init_db():
    import app.models  # noqa: F401 确保 Base.metadata 包含所有表
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    # 插入测试所需的最小数据：1 个分类 + 1 个菜品 + root 管理员 + rootroot 超级管理员
    from app.models.user import User
    from app.models.menu import MenuCategory, MenuItem
    from app.services.auth_service import _hash_password
    async with TestSessionLocal() as db:
        db.add(MenuCategory(name="热销", sort_order=0))
        db.add(MenuItem(name="宫保鸡丁", price=28.0, category="热销", stock=100))
        db.add(User(
            username="root",
            password=_hash_password("123456"),
            role="admin",
            need_change_password=False,
        ))
        db.add(User(
            username="rootroot",
            password=_hash_password("rootroot"),
            role="superadmin",
            need_change_password=False,
        ))
        await db.commit()


async def _close_db():
    await test_engine.dispose()


class TestHealth:
    def test_health_check(self):
        r = client.get("/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "ok"


def get_captcha_code() -> tuple[str, str]:
    """获取一个验证码并返回正确答案（优先从 Redis 读取，否则从内存回退缓存读取）"""
    r = client.get("/api/v1/auth/captcha")
    assert r.status_code == 200, f"Captcha failed: {r.text}"
    data = r.json()
    captcha_id = data["captcha_id"]
    cache_key = f"{CAPTCHA_KEY_PREFIX}{captcha_id}"

    # 优先从 Redis 读取
    try:
        import redis
        redis_client = redis.Redis(host='localhost', port=6379, db=0, decode_responses=True)
        code = redis_client.get(cache_key)
        if code:
            return captcha_id, code
    except Exception:
        pass

    # Redis 不可用时从内存缓存读取
    item = _memory_cache.get(cache_key)
    assert item is not None, "Captcha not found in cache"
    return captcha_id, item[0]


def register_user(username: str, password: str = "123456") -> dict:
    """注册一个测试用户"""
    r = client.post("/api/v1/auth/register", json={
        "username": username,
        "password": password,
        "gender": "unknown",
    })
    assert r.status_code == 200, f"Register failed: {r.text}"
    return r.json()["user"]


def login_and_get_token(username: str, password: str = "123456") -> str:
    """登录并返回 JWT"""
    captcha_id, code = get_captcha_code()
    r = client.post("/api/v1/auth/login", json={
        "username": username,
        "password": password,
        "captcha_id": captcha_id,
        "captcha_code": code,
    })
    assert r.status_code == 200, f"Login failed: {r.text}"
    token = r.json().get("token")
    assert token, "登录响应中缺少 token"
    return token


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


class TestAuth:
    def test_register_and_login(self):
        import uuid
        test_uname = f"test_{uuid.uuid4().hex[:8]}"
        
        # 注册
        r = client.post("/api/v1/auth/register", json={
            "username": test_uname,
            "password": "123456",
            "phone": "13800138001",
            "gender": "unknown"
        })
        assert r.status_code == 200, f"Register failed: {r.text}"
        
        # 登录
        captcha_id, code = get_captcha_code()
        r = client.post("/api/v1/auth/login", json={
            "username": test_uname,
            "password": "123456",
            "role": "customer",
            "captcha_id": captcha_id,
            "captcha_code": code,
        })
        assert r.status_code == 200, f"Login failed: {r.text}"
        data = r.json()
        assert data["user"]["username"] == test_uname
    
    def test_duplicate_register(self):
        import uuid
        test_uname = f"dup_{uuid.uuid4().hex[:8]}"
        
        client.post("/api/v1/auth/register", json={
            "username": test_uname,
            "password": "123456",
            "gender": "unknown"
        })
        
        r = client.post("/api/v1/auth/register", json={
            "username": test_uname,
            "password": "123456",
            "gender": "unknown"
        })
        assert r.status_code in (400, 422), f"Expected 400/422, got {r.status_code}"
    
    def test_wrong_password(self):
        import uuid
        test_uname = f"wp_{uuid.uuid4().hex[:8]}"
        
        client.post("/api/v1/auth/register", json={
            "username": test_uname,
            "password": "123456",
            "gender": "unknown"
        })
        
        captcha_id, code = get_captcha_code()
        r = client.post("/api/v1/auth/login", json={
            "username": test_uname,
            "password": "wrongpwd",
            "captcha_id": captcha_id,
            "captcha_code": code,
        })
        assert r.status_code == 401


class TestMenu:
    def test_get_menu(self):
        r = client.get("/api/v1/menu")
        assert r.status_code == 200
        items = r.json()
        assert isinstance(items, list)
        if len(items) > 0:
            item = items[0]
            assert all(k in item for k in ["id", "name", "price", "category", "stock"])


class TestSystem:
    def test_startup_time(self):
        r = client.get("/api/v1/system/startup")
        assert r.status_code == 200
        data = r.json()
        assert "startup_time" in data


class TestOrders:
    def test_order_flow(self):
        import uuid
        test_uname = f"order_{uuid.uuid4().hex[:8]}"

        # 注册并登录，获取 JWT
        register_user(test_uname)
        token = login_and_get_token(test_uname)
        headers = auth_headers(token)

        # 获取菜单
        r = client.get("/api/v1/menu")
        items = r.json()
        if not items:
            pytest.skip("No menu items available")

        # 创建订单
        cart_items = [{
            "menu_item_id": items[0]["id"],
            "name": items[0]["name"],
            "quantity": 2,
            "unit_price": items[0]["price"]
        }]
        r = client.post("/api/v1/order", json={"items": cart_items}, headers=headers)
        assert r.status_code == 200, f"Order create failed: {r.text}"
        order = r.json()
        assert "id" in order

        # 查询订单列表
        r = client.get("/api/v1/orders", headers=headers)
        assert r.status_code == 200
        data = r.json()
        assert "items" in data and "total" in data
        assert data["total"] >= 1

        # 查询订单详情
        r = client.get(f"/api/v1/order/{order['id']}", headers=headers)
        assert r.status_code == 200

    def test_orders_reject_forged_headers(self):
        """伪造 X-User-ID 头（无 JWT）应被拒绝"""
        r = client.get("/api/v1/orders", headers={"X-User-ID": "1", "X-User-Role": "admin"})
        assert r.status_code == 401


class TestSuperAdmin:
    def test_superadmin_reset_root_password(self):
        """超级管理员可将 root 密码重置为初始值 123456"""
        token = login_and_get_token("rootroot", "rootroot")
        r = client.post("/api/v1/admin/reset-root-password", headers=auth_headers(token))
        assert r.status_code == 200, f"Reset failed: {r.text}"
        # 重置后 root 可用初始密码登录
        root_token = login_and_get_token("root", "123456")
        assert root_token

    def test_admin_cannot_reset(self):
        """普通管理员无权重置"""
        token = login_and_get_token("root", "123456")
        r = client.post("/api/v1/admin/reset-root-password", headers=auth_headers(token))
        assert r.status_code == 403

    def test_customer_cannot_reset(self):
        """普通用户无权重置"""
        import uuid
        uname = f"cust_{uuid.uuid4().hex[:8]}"
        register_user(uname)
        token = login_and_get_token(uname)
        r = client.post("/api/v1/admin/reset-root-password", headers=auth_headers(token))
        assert r.status_code == 403

    def test_superadmin_username_reserved(self):
        """超级管理员用户名不可注册"""
        r = client.post("/api/v1/auth/register", json={
            "username": "rootroot",
            "password": "whatever",
            "gender": "unknown",
        })
        assert r.status_code in (400, 422)


class TestAdmin:
    @staticmethod
    def _admin_headers() -> dict:
        """以默认管理员 root 登录获取管理员 JWT"""
        token = login_and_get_token("root", "123456")
        return auth_headers(token)

    def test_admin_menu_list(self):
        r = client.get("/api/v1/admin/menu", headers=self._admin_headers())
        assert r.status_code == 200
        items = r.json()
        assert isinstance(items, list)

    def test_admin_orders_list(self):
        r = client.get("/api/v1/admin/orders", headers=self._admin_headers())
        assert r.status_code == 200
        data = r.json()
        assert "items" in data
        assert "total" in data
        assert isinstance(data["items"], list)

    def test_admin_auth_reject(self):
        import uuid
        test_uname = f"cust_{uuid.uuid4().hex[:8]}"
        register_user(test_uname)
        token = login_and_get_token(test_uname)
        r = client.get("/api/v1/admin/menu", headers=auth_headers(token))
        assert r.status_code == 403


class TestChatQuota:
    """智能聊天次数配额 + 超级管理员用户管理"""

    @staticmethod
    def _register_and_token() -> tuple[str, str]:
        import uuid
        uname = f"quota_{uuid.uuid4().hex[:8]}"
        register_user(uname)
        return uname, login_and_get_token(uname)

    @staticmethod
    def _set_quota(username: str, n: int):
        import asyncio

        async def _update():
            from sqlalchemy import select
            from app.models.user import User
            async with TestSessionLocal() as db:
                result = await db.execute(select(User).where(User.username == username))
                user = result.scalar_one()
                user.chat_quota = n
                await db.commit()

        asyncio.run(_update())

    def test_chat_consumes_quota(self):
        """普通用户发送一次智能聊天，剩余次数 -1"""
        uname, token = self._register_and_token()
        r = client.post(
            "/api/v1/ai/chat",
            json={"message": "清空购物车", "cart": []},
            headers=auth_headers(token),
        )
        assert r.status_code == 200, r.text

        sa_token = login_and_get_token("rootroot", "rootroot")
        r = client.get("/api/v1/admin/user-quotas", headers=auth_headers(sa_token))
        assert r.status_code == 200
        item = next(i for i in r.json() if i["username"] == uname)
        from app.ai.quota import INITIAL_QUOTA
        assert item["chat_quota"] == INITIAL_QUOTA - 1

    def test_quota_exhausted_returns_400(self):
        """次数为 0 时发送，返回 400 及提示文案"""
        uname, token = self._register_and_token()
        self._set_quota(uname, 0)
        r = client.post(
            "/api/v1/ai/chat",
            json={"message": "清空购物车", "cart": []},
            headers=auth_headers(token),
        )
        assert r.status_code == 422
        assert "聊天次数不足" in r.json()["detail"]

    def test_recharge_and_delete_user(self):
        """超管充值 100 次、删除用户；普通管理员无权操作"""
        uname, _ = self._register_and_token()
        sa_token = login_and_get_token("rootroot", "rootroot")

        quotas = client.get("/api/v1/admin/user-quotas", headers=auth_headers(sa_token)).json()
        uid = next(i["id"] for i in quotas if i["username"] == uname)

        r = client.post(f"/api/v1/admin/user-quotas/{uid}/recharge", headers=auth_headers(sa_token))
        assert r.status_code == 200
        from app.ai.quota import INITIAL_QUOTA, RECHARGE_AMOUNT
        assert r.json()["chat_quota"] == INITIAL_QUOTA + RECHARGE_AMOUNT

        admin_token = login_and_get_token("root", "123456")
        r = client.get("/api/v1/admin/user-quotas", headers=auth_headers(admin_token))
        assert r.status_code == 403

        r = client.delete(f"/api/v1/admin/users/{uid}", headers=auth_headers(sa_token))
        assert r.status_code == 200
        quotas = client.get("/api/v1/admin/user-quotas", headers=auth_headers(sa_token)).json()
        assert all(i["username"] != uname for i in quotas)

    def test_superadmin_change_password_only_once(self):
        """超级管理员首次强制改密后，不允许再次修改；且新密码不得与初始密码相同"""
        import asyncio
        import uuid
        from app.models.user import User
        from app.services.auth_service import _hash_password

        uname = f"sa_{uuid.uuid4().hex[:8]}"

        async def _create():
            async with TestSessionLocal() as db:
                db.add(User(
                    username=uname,
                    password=_hash_password("oldpass1"),
                    role="superadmin",
                    need_change_password=True,
                ))
                await db.commit()

        asyncio.run(_create())

        token = login_and_get_token(uname, "oldpass1")

        # 新密码与初始密码 rootroot 相同，被拒绝
        r = client.post(
            "/api/v1/auth/change-password",
            json={"new_password": "rootroot"},
            headers=auth_headers(token),
        )
        assert r.status_code == 422

        # 首次强制改密（不传旧密码）
        r = client.post(
            "/api/v1/auth/change-password",
            json={"new_password": "newpass123"},
            headers=auth_headers(token),
        )
        assert r.status_code == 200, r.text

        # 第二次修改被拒绝（仅允许一次）
        r = client.post(
            "/api/v1/auth/change-password",
            json={"old_password": "newpass123", "new_password": "another123"},
            headers=auth_headers(token),
        )
        assert r.status_code == 422

    def test_project_not_activated_gate(self):
        """超管未改初始密码时项目未启用：其他人登录被拒，仅超管本人可登录"""
        import asyncio
        import uuid
        from sqlalchemy import select
        from app.models.user import User

        async def _set_flag(value: bool):
            async with TestSessionLocal() as db:
                result = await db.execute(select(User).where(User.username == "rootroot"))
                sa = result.scalar_one()
                sa.need_change_password = value
                await db.commit()

        asyncio.run(_set_flag(True))
        try:
            # 普通用户登录被拒
            uname = f"gate_{uuid.uuid4().hex[:8]}"
            register_user(uname)
            captcha_id, code = get_captcha_code()
            r = client.post("/api/v1/auth/login", json={
                "username": uname,
                "password": "123456",
                "captcha_id": captcha_id,
                "captcha_code": code,
            })
            assert r.status_code == 422
            assert "项目未启用" in r.json()["detail"]

            # 管理员 root 登录同样被拒
            captcha_id, code = get_captcha_code()
            r = client.post("/api/v1/auth/login", json={
                "username": "root",
                "password": "123456",
                "captcha_id": captcha_id,
                "captcha_code": code,
            })
            assert r.status_code == 422
            assert "项目未启用" in r.json()["detail"]

            # 超级管理员本人可登录（进入后强制改密）
            token = login_and_get_token("rootroot", "rootroot")
            assert token
        finally:
            asyncio.run(_set_flag(False))
