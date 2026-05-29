# -*- coding: utf-8 -*-
"""
generate_content.py — 用 Claude API 批次擴充 JLPT 學習資料（離線生成工具）

用途：當「直接寫入的靜態資料」不夠時，用本腳本大量擴充各級別的單字。
產出格式與 db/N*.json 的 vocab 欄位完全相同，可直接合併。

使用方式：
    pip install anthropic
    export ANTHROPIC_API_KEY=sk-...
    # 為 N3 生成 30 個新單字並合併進 db/N3.json（自動跳過已存在的漢字）
    python scripts/generate_content.py --level N3 --count 30

設計重點：
    • 冪等：讀取現有 db/<level>.json，已存在的單字（以 kanji 判斷）會被跳過。
    • 安全：生成結果會先驗證欄位完整性，再寫回，避免污染資料庫。
    • 可離線降級：未安裝 anthropic 或未設金鑰時給出清楚指引，不會崩潰。
"""

from __future__ import annotations

import argparse
import json
import os
import sys

_DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "db")

_REQUIRED_FIELDS = {"kanji", "kana", "romaji", "chinese", "pos", "grammar", "usage", "examples"}

_PROMPT_TEMPLATE = """你是 JLPT 日文教材編輯。請為日檢 {level} 級別產生 {count} 個「常用且符合該級別難度」的新單字。
務必避開以下已存在的單字（漢字）：{existing}

以 JSON 陣列輸出，每個元素格式如下（不要任何多餘文字、不要 markdown 圍欄）：
{{
  "kanji": "漢字（若無漢字則與 kana 相同）",
  "kana": "假名唸法",
  "romaji": "羅馬拼音",
  "chinese": "繁體中文翻譯",
  "pos": "詞性（名詞／動詞（五段）／形容詞（い形）等）",
  "grammar": "該單字的核心文法重點（繁體中文說明）",
  "usage": "怎麼用、搭配、近義反義（繁體中文）",
  "examples": [
    {{"jp": "日文例句", "kana": "全假名唸法", "zh": "繁體中文翻譯"}},
    {{"jp": "第二個例句", "kana": "全假名唸法", "zh": "繁體中文翻譯"}}
  ]
}}
"""


def _load_level(level: str) -> dict:
    path = os.path.join(_DB_DIR, f"{level}.json")
    with open(path, encoding="utf-8") as fp:
        return json.load(fp)


def _save_level(level: str, payload: dict) -> None:
    path = os.path.join(_DB_DIR, f"{level}.json")
    with open(path, "w", encoding="utf-8") as fp:
        json.dump(payload, fp, ensure_ascii=False, indent=2)


def _validate(item: dict) -> bool:
    if not _REQUIRED_FIELDS.issubset(item):
        return False
    return isinstance(item.get("examples"), list) and len(item["examples"]) >= 1


def generate(level: str, count: int) -> None:
    try:
        import anthropic
    except ImportError:
        sys.exit("✗ 請先安裝：pip install anthropic")

    if not os.environ.get("ANTHROPIC_API_KEY"):
        sys.exit("✗ 請先設定環境變數 ANTHROPIC_API_KEY")

    payload = _load_level(level)
    existing = [w["kanji"] for w in payload.get("vocab", [])]

    client = anthropic.Anthropic()
    prompt = _PROMPT_TEMPLATE.format(
        level=level, count=count, existing="、".join(existing) or "（無）"
    )
    print(f"→ 呼叫 Claude 為 {level} 生成 {count} 個單字…")
    resp = client.messages.create(
        model="claude-opus-4-8",
        max_tokens=8000,
        messages=[{"role": "user", "content": prompt}],
    )
    text = resp.content[0].text.strip()
    # 去除可能的 ```json 圍欄
    if text.startswith("```"):
        text = text.split("```")[1].lstrip("json").strip()

    try:
        new_items = json.loads(text)
    except json.JSONDecodeError:
        sys.exit("✗ Claude 回傳非合法 JSON，請重試或調低 count。")

    added, skipped = 0, 0
    for item in new_items:
        if not _validate(item):
            skipped += 1
            continue
        if item["kanji"] in existing:
            skipped += 1
            continue
        payload.setdefault("vocab", []).append(item)
        existing.append(item["kanji"])
        added += 1

    _save_level(level, payload)
    print(f"✓ {level}.json 新增 {added} 字（跳過 {skipped}）。目前共 {len(payload['vocab'])} 字。")


def main() -> None:
    parser = argparse.ArgumentParser(description="用 Claude API 擴充 JLPT 單字庫")
    parser.add_argument("--level", required=True, choices=["N1", "N2", "N3", "N4", "N5"])
    parser.add_argument("--count", type=int, default=20)
    args = parser.parse_args()
    generate(args.level, args.count)


if __name__ == "__main__":
    main()
