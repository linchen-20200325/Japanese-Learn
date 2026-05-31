# -*- coding: utf-8 -*-
"""
data.py — JLPT 日文學習資料層（N1 ~ N5）

本模組為「資料存取層」，負責從 `db/` 目錄下的 JSON 資料庫載入
單字、文法、情境短文／文章與 50 音，並提供統一的存取介面。

資料庫結構（每個級別一個檔案）：
    db/N5.json, db/N4.json, db/N3.json, db/N2.json, db/N1.json
        {
          "level": "N5",
          "vocab":    [ {kanji, kana, romaji, chinese, pos, grammar, usage,
                          examples:[{jp, kana, zh}, ...]}, ... ],
          "grammar":  [ {point, meaning, usage,
                          examples:[{jp, kana, zh}, ...]}, ... ],
          "passages": [ {title, type("短文"/"文章"),
                          sentences:[{jp, kana, zh}, ...]}, ... ]
        }
    db/gojuon.json  →  {seion, dakuon, handakuon, yoon}

每一筆單字皆含：
    level   : 級別 (N1 ~ N5)
    kanji   : 日文漢字
    kana    : 假名（唸法）
    romaji  : 羅馬拼音
    chinese : 中文翻譯
    grammar : 該單字搭配的核心文法重點
    usage   : 使用方式說明（單字如何用）
    examples: 例句清單（每句含 jp 日文、kana 唸法、zh 中文）

存取一律透過 load_vocab / load_grammar / load_passages / load_gojuon，
禁止外部直接讀取私有快取。
"""

import json
import os
from functools import lru_cache
from typing import Dict, List

# 資料庫目錄（與本檔同層的 db/）
_DB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "db")


# ---------------------------------------------------------------------------
# 級別中繼資料：顯示名稱、主題色、簡介
# ---------------------------------------------------------------------------
LEVELS: Dict[str, Dict[str, str]] = {
    "N5": {"label": "N5 基礎", "color": "#4CAF50", "desc": "日文入門：50 音、基本問候與生活單字。"},
    "N4": {"label": "N4 初級", "color": "#2196F3", "desc": "初級會話：日常情境與基礎文型。"},
    "N3": {"label": "N3 中級", "color": "#FF9800", "desc": "承上啟下：複雜句型與抽象語彙。"},
    "N2": {"label": "N2 進階", "color": "#9C27B0", "desc": "進階閱讀：書面語與商務日文。"},
    "N1": {"label": "N1 進階最高峰", "color": "#F44336", "desc": "母語級：高階語彙、慣用句與正式文書。"},
}

# 級別在下拉選單中的呈現順序（由淺入深）
LEVEL_ORDER: List[str] = ["N5", "N4", "N3", "N2", "N1"]


# ---------------------------------------------------------------------------
# 低階載入（含快取，避免重複讀檔）
# ---------------------------------------------------------------------------
@lru_cache(maxsize=None)
def _load_json(filename: str) -> dict:
    """讀取 db/ 下的單一 JSON 檔；找不到時回傳空 dict。"""
    path = os.path.join(_DB_DIR, filename)
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as fp:
        return json.load(fp)


@lru_cache(maxsize=None)
def _load_level(level: str) -> dict:
    """載入指定級別的完整資料（vocab / grammar / passages）。"""
    return _load_json(f"{level}.json")


# ---------------------------------------------------------------------------
# 公開存取介面
# ---------------------------------------------------------------------------
def load_vocab(level: str) -> List[Dict]:
    """載入指定級別的單字清單，並補上 level 欄位。"""
    data = _load_level(level)
    return [{"level": level, **item} for item in data.get("vocab", [])]


def load_grammar(level: str) -> List[Dict]:
    """載入指定級別的核心文法清單。"""
    data = _load_level(level)
    return [{"level": level, **item} for item in data.get("grammar", [])]


def load_passages(level: str) -> List[Dict]:
    """載入指定級別的情境短文／文章清單（可能多篇）。"""
    data = _load_level(level)
    return [{"level": level, **item} for item in data.get("passages", [])]


def load_passage(level: str) -> Dict:
    """（相容介面）載入指定級別的第一篇短文。"""
    passages = load_passages(level)
    return passages[0] if passages else {"level": level}


def load_gojuon() -> Dict[str, List[Dict[str, str]]]:
    """
    載入 50 音表（基礎，N5 專用）。
    回傳含 seion / dakuon / handakuon / yoon 四組的字典。
    """
    return _load_json("gojuon.json")


def load_listening(lang: str) -> List[Dict]:
    """
    載入聽力範本（lang="ja" 日文 / "en" 英文）。

    db/listening.json 結構：
        {
          "ja": [ {title, level, lang, script:[{text, zh}, ...],
                    questions:[{q, options:[...], answer}]}, ... ],
          "en": [ ... 同上 ... ]
        }
    每段 script 的 text 為該語言原文、zh 為中文翻譯。
    """
    return _load_json("listening.json").get(lang, [])
