"""
人脸识别服务
基于 face_recognition（dlib）实现 128 维人脸特征提取与比对。
"""
import base64
import io
import json
import os
import uuid
from pathlib import Path
from typing import List, Optional, Tuple

import face_recognition
import numpy as np
from PIL import Image

from app.core.exceptions import BusinessException
from app.core.config import settings


# 默认相似度阈值（欧氏距离，越小越相似）
FACE_TOLERANCE = 0.55


def decode_base64_image(base64_str: str) -> np.ndarray:
    """将前端传来的 base64 图片解码为 RGB numpy 数组。"""
    if not base64_str:
        raise BusinessException("图片数据为空")
    if "," in base64_str:
        base64_str = base64_str.split(",", 1)[1]
    try:
        image_bytes = base64.b64decode(base64_str)
    except Exception as exc:
        raise BusinessException("图片数据格式不正确") from exc
    try:
        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
    except Exception as exc:
        raise BusinessException("无法解析图片") from exc
    return np.array(image)


def extract_face_encoding(base64_str: str) -> Optional[np.ndarray]:
    """从 base64 图片中提取 128 维人脸特征向量。

    返回 None 表示未检测到人脸。
    """
    image = decode_base64_image(base64_str)
    encodings = face_recognition.face_encodings(image)
    if not encodings:
        return None
    return encodings[0]


def encoding_to_list(encoding: np.ndarray) -> List[float]:
    return encoding.tolist()


def encoding_from_list(value) -> np.ndarray:
    if isinstance(value, str):
        value = json.loads(value)
    return np.array(value, dtype=np.float64)


def compare_face_distance(known_encoding: np.ndarray, unknown_encoding: np.ndarray) -> float:
    """计算两张脸特征向量的欧氏距离。"""
    known = np.asarray(known_encoding, dtype=np.float64)
    unknown = np.asarray(unknown_encoding, dtype=np.float64)
    return float(np.linalg.norm(known - unknown))


def save_face_image(base64_str: str, username: str) -> str:
    """保存人脸照片到 static/faces/{username}_{uuid}.jpg，返回相对路径。"""
    if "," in base64_str:
        base64_str = base64_str.split(",", 1)[1]
    image_bytes = base64.b64decode(base64_str)

    static_dir = Path(settings.static_dir or "static")
    faces_dir = static_dir / "faces"
    faces_dir.mkdir(parents=True, exist_ok=True)

    filename = f"{username}_{uuid.uuid4().hex[:8]}.jpg"
    file_path = faces_dir / filename
    with open(file_path, "wb") as f:
        f.write(image_bytes)

    return f"/static/faces/{filename}"


def find_best_face_match(
    unknown_encoding: np.ndarray,
    candidates: List[Tuple[int, np.ndarray]],
    tolerance: float = FACE_TOLERANCE,
) -> Optional[Tuple[int, float]]:
    """在候选特征中找出最相似的人脸。

    candidates: [(user_id, face_encoding), ...]
    返回 (user_id, distance) 或 None。
    """
    if not candidates:
        return None

    best_id: Optional[int] = None
    best_distance = float("inf")
    for user_id, known_encoding in candidates:
        distance = compare_face_distance(known_encoding, unknown_encoding)
        if distance < best_distance:
            best_distance = distance
            best_id = user_id

    if best_id is None or best_distance > tolerance:
        return None
    return best_id, best_distance
