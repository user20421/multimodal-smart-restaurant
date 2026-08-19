"""
AI 配置：双模型强绑定校验的单元测试

项目约定：配置了 BAILIAN_LLM_MODEL 就必须同时配置 BAILIAN_LLM_MODEL_X
（混合意图"餐厅经理"依赖更强模型），否则配置模块加载即报错，不做降级。
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import importlib

import dotenv
import pytest

import app.ai.config as ai_config


def test_model_x_required_when_llm_model_set(monkeypatch):
    """有 BAILIAN_LLM_MODEL 但缺 BAILIAN_LLM_MODEL_X -> 加载配置即 RuntimeError。"""
    fake_values = {"BAILIAN_LLM_MODEL": "some-model"}  # 有 A 无 X
    monkeypatch.setattr(dotenv, "dotenv_values", lambda *a, **k: fake_values)
    try:
        with pytest.raises(RuntimeError, match="BAILIAN_LLM_MODEL_X"):
            importlib.reload(ai_config)
    finally:
        # 还原模块到真实配置状态，避免影响其他测试
        monkeypatch.undo()
        importlib.reload(ai_config)


def test_model_x_binding_satisfied(monkeypatch):
    """双模型都配置 -> 正常加载，且 X 值正确读取。"""
    fake_values = {
        "BAILIAN_LLM_MODEL": "model-a",
        "BAILIAN_LLM_MODEL_X": "model-b",
    }
    monkeypatch.setattr(dotenv, "dotenv_values", lambda *a, **k: fake_values)
    try:
        module = importlib.reload(ai_config)
        assert module.BAILIAN_LLM_MODEL == "model-a"
        assert module.BAILIAN_LLM_MODEL_X == "model-b"
    finally:
        monkeypatch.undo()
        importlib.reload(ai_config)


def test_no_llm_model_no_check(monkeypatch):
    """对话模型也未配置（AI 整体不可用，走兜底回复）-> 不触发强校验。"""
    monkeypatch.setattr(dotenv, "dotenv_values", lambda *a, **k: {})
    try:
        module = importlib.reload(ai_config)
        assert module.BAILIAN_LLM_MODEL == ""
        assert module.BAILIAN_LLM_MODEL_X == ""
    finally:
        monkeypatch.undo()
        importlib.reload(ai_config)
