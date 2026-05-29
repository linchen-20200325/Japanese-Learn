# -*- coding: utf-8 -*-
"""
store.py — 學習進度資料層（卡片牌組建立、持久化、統計）

職責：
    • 從 ``data.py`` 的單字／文法建立 SRS 卡片牌組（deck）。
    • 進度持久化：本機寫入 ``progress.json``；雲端（Streamlit Cloud 暫存檔系統）
      則透過 App 的「下載／上傳備份」按鈕保存。
    • 提供學習統計（連續天數、今日新學、掌握度分布）給儀表板使用。

注意：本模組不直接相依 Streamlit，僅做純資料處理，方便單元測試。
"""

from __future__ import annotations

import datetime as _dt
import json
import os
from typing import Dict, List

import data
import srs

_PROGRESS_PATH = os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "progress.json"
)


# ---------------------------------------------------------------------------
# 卡片 ID 與牌組建立
# ---------------------------------------------------------------------------
def vocab_card_id(level: str, word: Dict) -> str:
    return f"{level}:vocab:{word.get('kanji') or word.get('kana')}"


def grammar_card_id(level: str, g: Dict) -> str:
    return f"{level}:grammar:{g.get('point')}"


def build_all_cards() -> Dict[str, Dict]:
    """
    掃描所有級別的單字與文法，建立「卡片範本」字典（id -> meta）。
    這只是來源資料的索引，實際排程狀態存在 progress store。
    """
    catalog: Dict[str, Dict] = {}
    for level in data.LEVEL_ORDER:
        for w in data.load_vocab(level):
            cid = vocab_card_id(level, w)
            catalog[cid] = {"type": "vocab", "level": level, "payload": w}
        for g in data.load_grammar(level):
            cid = grammar_card_id(level, g)
            catalog[cid] = {"type": "grammar", "level": level, "payload": g}
    return catalog


# ---------------------------------------------------------------------------
# 持久化（本機 JSON）
# ---------------------------------------------------------------------------
def default_store() -> Dict:
    """全新的空白進度檔結構。"""
    return {
        "cards": {},          # id -> SRS card
        "streak": 0,          # 連續學習天數
        "last_study": "",     # 最後學習日 ISO
        "daily": {},          # ISO日期 -> 當天複習張數
        "new_today": {},      # ISO日期 -> 當天新學張數
    }


def load_store() -> Dict:
    """從本機讀取進度；不存在或毀損時回傳空白結構。"""
    if not os.path.exists(_PROGRESS_PATH):
        return default_store()
    try:
        with open(_PROGRESS_PATH, encoding="utf-8") as fp:
            store = json.load(fp)
    except (json.JSONDecodeError, OSError):
        return default_store()
    # 補齊缺漏欄位，向前相容
    base = default_store()
    base.update(store)
    return base


def save_store(store: Dict) -> None:
    """寫回本機進度檔（雲端暫存環境仍會在重新部署後重置，故另提供備份匯出）。"""
    try:
        with open(_PROGRESS_PATH, "w", encoding="utf-8") as fp:
            json.dump(store, fp, ensure_ascii=False, indent=2)
    except OSError:
        pass  # 雲端唯讀／暫存環境忽略寫入失敗，改用匯出備份


# ---------------------------------------------------------------------------
# 卡片取得（lazy 建立）
# ---------------------------------------------------------------------------
def get_card(store: Dict, card_id: str, card_type: str, level: str) -> Dict:
    """取得卡片排程狀態；首次出現時自動建立新卡。"""
    card = store["cards"].get(card_id)
    if card is None:
        card = srs.new_card(card_id, card_type, level)
        store["cards"][card_id] = card
    return card


def review_card(store: Dict, card_id: str, card_type: str, level: str, quality: int) -> Dict:
    """對某卡片評分並更新排程、連續天數與每日統計。"""
    today = _dt.date.today()
    iso = today.isoformat()
    card = get_card(store, card_id, card_type, level)
    was_new = srs.is_new(card)
    srs.grade(card, quality, today=today)

    # 每日複習與新學統計
    store["daily"][iso] = store["daily"].get(iso, 0) + 1
    if was_new:
        store["new_today"][iso] = store["new_today"].get(iso, 0) + 1

    _update_streak(store, today)
    return card


def _update_streak(store: Dict, today: _dt.date) -> None:
    """更新連續學習天數：今天接續昨天則 +1，斷掉則重設為 1。"""
    last = store.get("last_study", "")
    iso = today.isoformat()
    if last == iso:
        return  # 今天已記錄過
    if last:
        try:
            last_date = _dt.date.fromisoformat(last)
            if (today - last_date).days == 1:
                store["streak"] = store.get("streak", 0) + 1
            else:
                store["streak"] = 1
        except ValueError:
            store["streak"] = 1
    else:
        store["streak"] = 1
    store["last_study"] = iso


# ---------------------------------------------------------------------------
# 統計（給儀表板）
# ---------------------------------------------------------------------------
def level_stats(store: Dict, level: str) -> Dict:
    """
    回傳某級別的掌握度統計：
        total / new / learning / young / mature / due_today
    """
    catalog = build_all_cards()
    ids = [cid for cid, m in catalog.items() if m["level"] == level]
    counts = {"total": len(ids), "new": 0, "learning": 0,
              "young": 0, "mature": 0, "due": 0, "studied": 0}
    today = _dt.date.today()
    for cid in ids:
        card = store["cards"].get(cid)
        if card is None:
            counts["new"] += 1
            continue
        counts["studied"] += 1
        counts[srs.mastery(card)] += 1
        if srs.is_due(card, today):
            counts["due"] += 1
    return counts


def overall_stats(store: Dict) -> Dict:
    """跨級別總覽：總卡數、已學、各掌握度、整體保留率、今日到期。"""
    cards = list(store["cards"].values())
    catalog = build_all_cards()
    today = _dt.date.today()
    due = sum(1 for c in cards if srs.is_due(c, today))
    by_mastery = {"new": 0, "learning": 0, "young": 0, "mature": 0}
    for c in cards:
        by_mastery[srs.mastery(c)] = by_mastery.get(srs.mastery(c), 0) + 1
    return {
        "catalog_total": len(catalog),
        "studied": len(cards),
        "due_today": due,
        "streak": store.get("streak", 0),
        "retention": srs.retention_rate(cards),
        "mastery": by_mastery,
        "reviews_total": sum(c.get("reviews", 0) for c in cards),
    }
