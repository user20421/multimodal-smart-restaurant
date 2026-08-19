"""
对话历史滚动摘要单元测试

使用本地 MongoDB（必需依赖），mock 摘要 LLM 调用。
覆盖：积压触发摘要、阈值以下不摘要、摘要注入历史、清空时摘要一并删除。
"""
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "../.."))

import asyncio

import pytest

from app.ai import chat_store

TEST_USER = 900000001

FAKE_SUMMARY = "顾客喜欢微辣，讨论过宫保鸡丁和米饭。"


@pytest.fixture
async def cleanup():
    yield
    await chat_store.clear_history(TEST_USER)


async def _append_rounds(user_id: int, rounds: int) -> None:
    """追加 rounds 轮问答（每轮 2 条），直接写库不触发后台任务。"""
    for i in range(rounds):
        await asyncio.to_thread(
            chat_store._append_history_sync,
            user_id,
            [
                {"role": "user", "content": f"问题{i}"},
                {"role": "assistant", "content": f"回答{i}"},
            ],
        )


async def test_summary_triggered_when_backlog(cleanup, monkeypatch):
    """原文超过阈值：最旧的 10 条被压缩进摘要，剩余 14 条原文"""
    async def fake_llm(old_summary, oldest):
        assert len(oldest) == chat_store.SUMMARY_BATCH_SIZE
        return FAKE_SUMMARY

    monkeypatch.setattr(chat_store, "_run_summary_llm", fake_llm)

    await _append_rounds(TEST_USER, 12)  # 24 条 > 20 阈值
    await chat_store._summarize_if_needed(TEST_USER)

    remaining = await asyncio.to_thread(chat_store._count_sync, TEST_USER)
    assert remaining == 24 - chat_store.SUMMARY_BATCH_SIZE
    summary = await asyncio.to_thread(chat_store._get_summary_sync, TEST_USER)
    assert summary == FAKE_SUMMARY


async def test_no_summary_below_threshold(cleanup, monkeypatch):
    """未超阈值：不做摘要"""
    async def fake_llm(old_summary, oldest):  # pragma: no cover - 不应被调用
        raise AssertionError("阈值以下不应调用摘要 LLM")

    monkeypatch.setattr(chat_store, "_run_summary_llm", fake_llm)

    await _append_rounds(TEST_USER, 2)  # 4 条
    await chat_store._summarize_if_needed(TEST_USER)

    remaining = await asyncio.to_thread(chat_store._count_sync, TEST_USER)
    assert remaining == 4
    summary = await asyncio.to_thread(chat_store._get_summary_sync, TEST_USER)
    assert summary == ""


async def test_summary_injected_into_history(cleanup, monkeypatch):
    """load_history 应把摘要作为 system 条目置于最前"""
    async def fake_llm(old_summary, oldest):
        return FAKE_SUMMARY

    monkeypatch.setattr(chat_store, "_run_summary_llm", fake_llm)

    await _append_rounds(TEST_USER, 12)
    await chat_store._summarize_if_needed(TEST_USER)

    history = await chat_store.load_history(TEST_USER)
    assert history[0]["role"] == "system"
    assert FAKE_SUMMARY in history[0]["content"]
    # 原文最多保留窗口大小
    assert len([h for h in history if h["role"] != "system"]) <= chat_store.config.CHAT_HISTORY_LIMIT


async def test_clear_history_removes_summary(cleanup, monkeypatch):
    """清空对话时摘要一并删除"""
    async def fake_llm(old_summary, oldest):
        return FAKE_SUMMARY

    monkeypatch.setattr(chat_store, "_run_summary_llm", fake_llm)

    await _append_rounds(TEST_USER, 12)
    await chat_store._summarize_if_needed(TEST_USER)
    await chat_store.clear_history(TEST_USER)

    remaining = await asyncio.to_thread(chat_store._count_sync, TEST_USER)
    summary = await asyncio.to_thread(chat_store._get_summary_sync, TEST_USER)
    assert remaining == 0
    assert summary == ""
