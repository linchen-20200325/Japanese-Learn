# -*- coding: utf-8 -*-
"""tests/test_data.py — 資料層與 db JSON 完整性測試。

只依賴 data.py（不 import app.py / ai.py，避免拉進 streamlit 依賴），
驗證每個級別的單字／文法／短文資料結構齊全、JSON 可解析、關鍵欄位非空。
跑法：pytest -q
"""

import json
import os

import pytest

import data

# 單字必備欄位（依 CLAUDE.md §3 架構規範，缺一不可）
VOCAB_REQUIRED = ("level", "kanji", "kana", "romaji", "chinese",
                  "grammar", "usage", "examples")
EXAMPLE_REQUIRED = ("jp", "kana", "zh")


# ---------------------------------------------------------------------------
# JSON 可解析性
# ---------------------------------------------------------------------------
def test_all_db_json_parseable():
    """db/ 下每個 JSON 檔都必須能被解析。"""
    db_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "db")
    files = [f for f in os.listdir(db_dir) if f.endswith(".json")]
    assert files, "db/ 目錄下找不到任何 JSON 檔"
    for fn in files:
        with open(os.path.join(db_dir, fn), encoding="utf-8") as fp:
            json.load(fp)  # 解析失敗會直接拋例外讓測試失敗


@pytest.mark.parametrize("level", data.LEVEL_ORDER)
def test_each_level_has_vocab(level):
    """每個級別至少要有單字資料。"""
    vocab = data.load_vocab(level)
    assert len(vocab) > 0, f"{level} 沒有任何單字"


# ---------------------------------------------------------------------------
# 單字欄位完整性
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("level", data.LEVEL_ORDER)
def test_vocab_fields_complete(level):
    """每筆單字八大欄位齊全，且 kanji/kana/chinese 非空。"""
    for w in data.load_vocab(level):
        for field in VOCAB_REQUIRED:
            assert field in w, f"{level} 單字 {w.get('kanji', '?')} 缺欄位 {field}"
        assert w["level"] == level, f"{level} 單字 level 欄位不符：{w['level']}"
        for key in ("kanji", "kana", "chinese"):
            assert str(w[key]).strip(), f"{level} 單字 {w.get('kanji', '?')} 的 {key} 為空"


@pytest.mark.parametrize("level", data.LEVEL_ORDER)
def test_vocab_examples_structure(level):
    """每筆單字的 examples 為清單，且每句含 jp/kana/zh。"""
    for w in data.load_vocab(level):
        examples = w["examples"]
        assert isinstance(examples, list), f"{level} 單字 {w['kanji']} 的 examples 非清單"
        for ex in examples:
            for field in EXAMPLE_REQUIRED:
                assert field in ex, f"{level} 單字 {w['kanji']} 例句缺 {field}"


# ---------------------------------------------------------------------------
# 文法與短文
# ---------------------------------------------------------------------------
@pytest.mark.parametrize("level", data.LEVEL_ORDER)
def test_grammar_fields(level):
    """每筆文法須含 point 與 meaning 且非空。"""
    for g in data.load_grammar(level):
        assert g.get("point", "").strip(), f"{level} 有文法缺 point"
        assert g.get("meaning", "").strip(), f"{level} 文法 {g.get('point')} 缺 meaning"


@pytest.mark.parametrize("level", data.LEVEL_ORDER)
def test_passages_structure(level):
    """每篇短文須有 title 與非空 sentences，每句含 jp/zh。"""
    for p in data.load_passages(level):
        assert p.get("title", "").strip(), f"{level} 有短文缺 title"
        sentences = p.get("sentences", [])
        assert sentences, f"{level} 短文 {p.get('title')} 沒有句子"
        for s in sentences:
            assert s.get("jp", "").strip(), f"{level} 短文 {p['title']} 有句子缺 jp"
            assert "zh" in s, f"{level} 短文 {p['title']} 有句子缺 zh"


# ---------------------------------------------------------------------------
# 50 音
# ---------------------------------------------------------------------------
def test_gojuon_sections():
    """50 音四組皆存在且非空，每筆含 kana/romaji。"""
    gojuon = data.load_gojuon()
    for section in ("seion", "dakuon", "handakuon", "yoon"):
        rows = gojuon.get(section, [])
        assert rows, f"50 音缺 {section} 或為空"
        for item in rows:
            assert item.get("kana", "").strip(), f"{section} 有項目缺 kana"
            assert item.get("romaji", "").strip(), f"{section} 有項目缺 romaji"


def test_levels_metadata_consistent():
    """LEVELS 與 LEVEL_ORDER 一致，且每級有 label/color/desc。"""
    assert set(data.LEVELS) == set(data.LEVEL_ORDER)
    for lv, meta in data.LEVELS.items():
        for key in ("label", "color", "desc"):
            assert meta.get(key), f"{lv} 的中繼資料缺 {key}"
