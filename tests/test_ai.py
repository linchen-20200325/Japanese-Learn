# -*- coding: utf-8 -*-
"""tests/test_ai.py — ai.py 純函式（解析／清理）測試。

ai.py 頂部 import streamlit，CI 未裝時整檔 skip（不影響 data 測試）。
只測不需金鑰／網路的純函式：key 清理、JSON 抽取、mermaid 清潔、字幕清理。
跑法：pytest -q
"""

import pytest

# streamlit 未安裝時跳過整個模組（ai.py import streamlit）
pytest.importorskip("streamlit")

import ai  # noqa: E402


# ---------------------------------------------------------------------------
# _clean_keys：抽出 AIza 開頭、長度≥30 的 key，去重保序、剝引號雜質
# ---------------------------------------------------------------------------
def _key(suffix: str) -> str:
    """造一把長度≥30 的假 key。"""
    k = "AIza" + suffix
    return k + "x" * (31 - len(k)) if len(k) < 31 else k


def test_clean_keys_extracts_valid():
    k = _key("ABCDEF123456")
    assert ai._clean_keys(k) == [k]


def test_clean_keys_rejects_short_or_nonprefixed():
    assert ai._clean_keys("shortkey") == []
    assert ai._clean_keys("AIza123") == []  # 太短
    assert ai._clean_keys("BIzaXXXXXXXXXXXXXXXXXXXXXXXXXXXXX") == []  # 前綴不符


def test_clean_keys_dedup_and_order():
    a, b = _key("AAAAAAAAAAAA"), _key("BBBBBBBBBBBB")
    assert ai._clean_keys([a, b, a]) == [a, b]


def test_clean_keys_splits_delimited_and_strips_quotes():
    a, b = _key("AAAAAAAAAAAA"), _key("BBBBBBBBBBBB")
    assert ai._clean_keys(f'"{a}", {b}') == [a, b]


def test_clean_keys_from_dict_values():
    a = _key("AAAAAAAAAAAA")
    assert ai._clean_keys({"GEMINI_API_KEY": a}) == [a]


def test_clean_keys_none_returns_empty():
    assert ai._clean_keys(None) == []


# ---------------------------------------------------------------------------
# extract_json_array：容忍程式碼圍欄與前後雜訊
# ---------------------------------------------------------------------------
def test_extract_json_array_plain():
    assert ai.extract_json_array('[{"a": 1}]') == [{"a": 1}]


def test_extract_json_array_with_fence():
    txt = '前言\n```json\n[{"x": "あ"}]\n```\n後話'
    assert ai.extract_json_array(txt) == [{"x": "あ"}]


def test_extract_json_array_with_surrounding_noise():
    txt = 'ここ→ [1, 2, 3] ←おわり'
    assert ai.extract_json_array(txt) == [1, 2, 3]


def test_extract_json_array_invalid_raises():
    with pytest.raises(Exception):
        ai.extract_json_array("not json at all")


# ---------------------------------------------------------------------------
# parse_blocks：抽 mermaid 與 flashcards
# ---------------------------------------------------------------------------
def test_parse_blocks_extracts_both():
    text = (
        "```mermaid\nflowchart LR\n  root((\"テスト\"))\n```\n"
        "```json\n{\"flashcards\": [{\"id\": 1, \"sentence\": \"こんにちは\"}]}\n```"
    )
    mermaid, cards = ai.parse_blocks(text)
    assert mermaid and "flowchart LR" in mermaid
    assert cards == [{"id": 1, "sentence": "こんにちは"}]


def test_parse_blocks_missing_returns_none():
    mermaid, cards = ai.parse_blocks("沒有任何區塊")
    assert mermaid is None and cards is None


# ---------------------------------------------------------------------------
# _sanitize_mermaid：節點內半形括號轉全形、mindmap→flowchart
# ---------------------------------------------------------------------------
def test_sanitize_mermaid_converts_halfwidth_brackets():
    out = ai._sanitize_mermaid('n0["注文(ちゅうもん) | 點餐"]')
    assert "(" not in out and ")" not in out
    assert "（ちゅうもん）" in out


def test_sanitize_mermaid_mindmap_to_flowchart():
    out = ai._sanitize_mermaid("mindmap\n  root")
    assert out.splitlines()[0] == "flowchart LR"


def test_sanitize_mermaid_empty():
    assert ai._sanitize_mermaid("") == ""


# ---------------------------------------------------------------------------
# clean_subtitle_text：移除序號／時間軸／HTML 標籤／空行
# ---------------------------------------------------------------------------
def test_clean_subtitle_strips_srt_metadata():
    raw = (
        "1\n"
        "00:00:01,000 --> 00:00:03,000\n"
        "<i>おはよう</i>\n"
        "\n"
        "2\n"
        "00:00:04,000 --> 00:00:05,000\n"
        "ございます\n"
    )
    out = ai.clean_subtitle_text(raw)
    assert out == "おはよう\nございます"
    assert "-->" not in out and "<i>" not in out
