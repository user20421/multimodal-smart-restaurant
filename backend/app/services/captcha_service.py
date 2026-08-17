"""
图片验证码服务
生成随机验证码图片，并将答案缓存到 Redis（Redis 不可用时回退到内存缓存）
"""
import io
import base64
import random
import string
import uuid
from datetime import datetime, timedelta

from PIL import Image, ImageDraw, ImageFont
from app.core.redis import get_redis
from app.core.logging_config import get_logger


logger = get_logger(__name__)

# 排除易混淆字符：0/O, 1/I/l
CAPTCHA_CHARS = string.ascii_uppercase + string.digits
CAPTCHA_CHARS = "".join(c for c in CAPTCHA_CHARS if c not in "0O1Il")

CAPTCHA_LENGTH = 4
CAPTCHA_TTL_SECONDS = 120
CAPTCHA_KEY_PREFIX = "captcha:"
IMAGE_WIDTH = 120
IMAGE_HEIGHT = 44
FONT_SIZE = 28

# Redis 不可用时的内存回退缓存（仅用于测试或开发环境）
_memory_cache: dict[str, tuple[str, datetime]] = {}


def _random_color(min_val: int = 50, max_val: int = 200):
    """生成随机 RGB 颜色"""
    return (
        random.randint(min_val, max_val),
        random.randint(min_val, max_val),
        random.randint(min_val, max_val),
    )


def _random_light_color():
    """生成浅色（用于背景）"""
    return _random_color(180, 245)


def _random_dark_color():
    """生成深色（用于文字）"""
    return _random_color(20, 120)


def generate_captcha_image(code: str) -> bytes:
    """
    使用 Pillow 生成验证码图片
    返回 PNG 字节流
    """
    # 随机浅色背景
    image = Image.new("RGB", (IMAGE_WIDTH, IMAGE_HEIGHT), _random_light_color())
    draw = ImageDraw.Draw(image)

    # 添加背景噪点
    for _ in range(200):
        x = random.randint(0, IMAGE_WIDTH - 1)
        y = random.randint(0, IMAGE_HEIGHT - 1)
        draw.point((x, y), fill=_random_color(150, 220))

    # 添加干扰线
    for _ in range(6):
        x1 = random.randint(0, IMAGE_WIDTH)
        y1 = random.randint(0, IMAGE_HEIGHT)
        x2 = random.randint(0, IMAGE_WIDTH)
        y2 = random.randint(0, IMAGE_HEIGHT)
        draw.line((x1, y1, x2, y2), fill=_random_color(100, 180), width=1)

    # 尝试加载字体，失败则使用默认字体
    try:
        font = ImageFont.truetype("DejaVuSans-Bold.ttf", FONT_SIZE)
    except Exception:
        try:
            font = ImageFont.truetype("arial.ttf", FONT_SIZE)
        except Exception:
            font = ImageFont.load_default()

    # 逐个字符绘制，加入随机偏移和旋转
    char_width = IMAGE_WIDTH // CAPTCHA_LENGTH
    for i, char in enumerate(code):
        # 创建单个字符图片
        char_img = Image.new("RGBA", (char_width, IMAGE_HEIGHT), (255, 255, 255, 0))
        char_draw = ImageDraw.Draw(char_img)
        char_draw.text(
            (char_width // 2, IMAGE_HEIGHT // 2),
            char,
            font=font,
            fill=_random_dark_color(),
            anchor="mm",
        )

        # 随机旋转
        angle = random.randint(-30, 30)
        rotated = char_img.rotate(angle, expand=False, resample=Image.BICUBIC)

        # 随机位置偏移
        x_offset = random.randint(-4, 4)
        y_offset = random.randint(-4, 4)
        paste_x = i * char_width + char_width // 2 - rotated.width // 2 + x_offset
        paste_y = IMAGE_HEIGHT // 2 - rotated.height // 2 + y_offset

        image.paste(rotated, (paste_x, paste_y), rotated)

    # 添加前景干扰线（覆盖在文字上，增加识别难度）
    for _ in range(3):
        x1 = random.randint(0, IMAGE_WIDTH)
        y1 = random.randint(0, IMAGE_HEIGHT)
        x2 = random.randint(0, IMAGE_WIDTH)
        y2 = random.randint(0, IMAGE_HEIGHT)
        draw.line((x1, y1, x2, y2), fill=_random_color(80, 160), width=1)

    # 输出为 PNG 字节
    buffer = io.BytesIO()
    image.save(buffer, format="PNG")
    return buffer.getvalue()


def _memory_set(key: str, code: str, ttl_seconds: int):
    """内存缓存：设置验证码"""
    expire_at = datetime.utcnow() + timedelta(seconds=ttl_seconds)
    _memory_cache[key] = (code, expire_at)


def _memory_get(key: str) -> str | None:
    """内存缓存：获取验证码，过期自动清理"""
    now = datetime.utcnow()
    # 清理过期项
    expired_keys = [k for k, (_, exp) in _memory_cache.items() if exp < now]
    for k in expired_keys:
        _memory_cache.pop(k, None)

    item = _memory_cache.get(key)
    if item is None:
        return None
    code, expire_at = item
    if expire_at < now:
        _memory_cache.pop(key, None)
        return None
    return code


def _memory_delete(key: str):
    """内存缓存：删除验证码"""
    _memory_cache.pop(key, None)


async def create_captcha() -> dict:
    """
    生成验证码并缓存到 Redis（Redis 不可用时回退到内存缓存）
    返回 {captcha_id, image_base64}
    """
    code = "".join(random.choices(CAPTCHA_CHARS, k=CAPTCHA_LENGTH))
    captcha_id = str(uuid.uuid4())

    image_bytes = generate_captcha_image(code)
    image_base64 = "data:image/png;base64," + base64.b64encode(image_bytes).decode("utf-8")

    key = f"{CAPTCHA_KEY_PREFIX}{captcha_id}"
    try:
        redis_client = await get_redis()
        await redis_client.set(
            key,
            code,
            ex=CAPTCHA_TTL_SECONDS,
        )
    except Exception as e:
        logger.warning(f"Redis 不可用，验证码回退到内存缓存: {e}")
        _memory_set(key, code, CAPTCHA_TTL_SECONDS)

    return {
        "captcha_id": captcha_id,
        "image_base64": image_base64,
    }


async def verify_captcha(captcha_id: str, captcha_code: str) -> bool:
    """
    校验验证码
    校验成功后立即删除，防止重放
    """
    if not captcha_id or not captcha_code:
        return False

    key = f"{CAPTCHA_KEY_PREFIX}{captcha_id}"
    stored_code = None

    try:
        redis_client = await get_redis()
        stored_code = await redis_client.get(key)
        if stored_code is not None:
            await redis_client.delete(key)
    except Exception as e:
        logger.warning(f"Redis 校验失败，尝试内存缓存: {e}")

    if stored_code is None:
        stored_code = _memory_get(key)
        _memory_delete(key)

    if stored_code is None:
        return False

    return stored_code.upper() == captcha_code.upper()
