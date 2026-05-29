# -*- coding: utf-8 -*-
"""
srs.py — 科學間隔重複引擎（Spaced Repetition System, SM-2）

本模組為跨功能共用的「記憶排程核心」，不依賴 Streamlit，可獨立測試。
任何學習項目（單字、文法、句子）只要給定唯一 ``card_id`` 即可納入排程。

設計理念（學習科學）：
    • 主動回憶（Active Recall）：複習時先想答案，再翻面評分。
    • 間隔重複（Spaced Repetition）：答對拉長間隔、答錯縮短，逼近遺忘曲線。
    • 三鍵評分對應 SM-2 品質分數：
        忘記 (again) → q=2（重置）、普通 (good) → q=4、簡單 (easy) → q=5。

卡片資料結構（dict，可直接 JSON 序列化）：
    {
        "id":        str,    # 唯一鍵，如 "N5:vocab:私"
        "type":      str,    # "vocab" / "grammar" / "sentence"
        "level":     str,    # N1~N5
        "ease":      float,  # 易度因子（>=1.3，預設 2.5）
        "interval":  int,    # 下次間隔（天）
        "reps":      int,    # 連續答對次數
        "lapses":    int,    # 遺忘（答錯）累計次數
        "due":       str,    # 下次到期日 ISO（YYYY-MM-DD）
        "last":      str,    # 上次複習日 ISO
        "reviews":   int,    # 總複習次數
    }
"""

from __future__ import annotations

import datetime as _dt
from typing import Dict, List, Optional

# --- 評分常數（與 UI 三鍵對應）-------------------------------------------------
AGAIN = 2   # 忘記
GOOD = 4    # 普通
EASY = 5    # 簡單

MIN_EASE = 1.3
DEFAULT_EASE = 2.5


def _today() -> _dt.date:
    return _dt.date.today()


def _iso(d: _dt.date) -> str:
    return d.isoformat()


def new_card(card_id: str, card_type: str, level: str) -> Dict:
    """建立一張全新（尚未學習）的卡片，到期日為今天（可立即排入新卡）。"""
    return {
        "id": card_id,
        "type": card_type,
        "level": level,
        "ease": DEFAULT_EASE,
        "interval": 0,
        "reps": 0,
        "lapses": 0,
        "due": _iso(_today()),
        "last": "",
        "reviews": 0,
    }


def grade(card: Dict, quality: int, today: Optional[_dt.date] = None) -> Dict:
    """
    依 SM-2 演算法更新卡片狀態（就地修改並回傳同一個 dict）。

    quality：使用 AGAIN(2) / GOOD(4) / EASY(5)。
    回傳更新後的卡片；``due`` 為下一次應複習的日期。
    """
    today = today or _today()
    ease = card.get("ease", DEFAULT_EASE)

    if quality < 3:
        # 答錯：連勝歸零、隔天重來、遺忘次數 +1
        card["reps"] = 0
        card["interval"] = 1
        card["lapses"] = card.get("lapses", 0) + 1
    else:
        reps = card.get("reps", 0)
        if reps == 0:
            interval = 1
        elif reps == 1:
            interval = 6
        else:
            interval = round(card.get("interval", 1) * ease)
            if quality == EASY:
                interval = round(interval * 1.3)  # 「簡單」額外拉長
        card["interval"] = max(1, interval)
        card["reps"] = reps + 1

    # 更新易度因子（SM-2 公式），下限 1.3
    ease = ease + (0.1 - (5 - quality) * (0.08 + (5 - quality) * 0.02))
    card["ease"] = max(MIN_EASE, round(ease, 3))

    card["last"] = _iso(today)
    card["due"] = _iso(today + _dt.timedelta(days=card["interval"]))
    card["reviews"] = card.get("reviews", 0) + 1
    return card


def is_due(card: Dict, today: Optional[_dt.date] = None) -> bool:
    """卡片是否到期（到期日 <= 今天）。"""
    today = today or _today()
    try:
        due = _dt.date.fromisoformat(card.get("due", ""))
    except ValueError:
        return True
    return due <= today


def is_new(card: Dict) -> bool:
    """是否為尚未複習過的新卡。"""
    return card.get("reviews", 0) == 0


def mastery(card: Dict) -> str:
    """
    依連勝次數與間隔粗分掌握度，供統計與儀表板使用。
        new      : 尚未學習
        learning : 學習中（間隔 < 7 天）
        young    : 漸熟（間隔 7~20 天）
        mature   : 已掌握（間隔 >= 21 天）
    """
    if is_new(card):
        return "new"
    interval = card.get("interval", 0)
    if interval >= 21:
        return "mature"
    if interval >= 7:
        return "young"
    return "learning"


def retention_rate(cards: List[Dict]) -> Optional[float]:
    """
    估算整體保留率：成功複習次數 / 總複習次數。
    以 (reviews - lapses) / reviews 近似；無複習紀錄時回傳 None。
    """
    total_reviews = sum(c.get("reviews", 0) for c in cards)
    if total_reviews == 0:
        return None
    total_lapses = sum(c.get("lapses", 0) for c in cards)
    return max(0.0, (total_reviews - total_lapses) / total_reviews)


def build_session(
    cards: List[Dict],
    new_limit: int = 10,
    review_limit: int = 50,
    today: Optional[_dt.date] = None,
) -> List[Dict]:
    """
    建立今日複習佇列：先排到期的舊卡（最久沒複習優先），再補新卡。

    new_limit    : 今日最多引入幾張新卡（控制學習負擔，避免暴增）。
    review_limit : 今日最多複習幾張到期舊卡。
    """
    today = today or _today()
    due_old = [c for c in cards if not is_new(c) and is_due(c, today)]
    due_old.sort(key=lambda c: c.get("due", ""))
    new_cards = [c for c in cards if is_new(c)]

    session = due_old[:review_limit] + new_cards[:new_limit]
    return session


def forecast(cards: List[Dict], days: int = 7, today: Optional[_dt.date] = None) -> List[int]:
    """回傳未來 ``days`` 天每天的到期卡片數（含今天，index 0 = 今天）。"""
    today = today or _today()
    counts = [0] * days
    for c in cards:
        if is_new(c):
            continue
        try:
            due = _dt.date.fromisoformat(c.get("due", ""))
        except ValueError:
            continue
        delta = (due - today).days
        if delta < 0:
            counts[0] += 1  # 逾期者算今天
        elif delta < days:
            counts[delta] += 1
    return counts
