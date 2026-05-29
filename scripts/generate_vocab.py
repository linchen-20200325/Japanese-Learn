#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""批次生成日文單字庫：呼叫 Gemini API 為 vocab_wordlist.txt 內每個字補上假名／羅馬拼音／
諧音／造句／用法，結果寫進 vocab_bank.json，Streamlit「📖 單字庫」分頁即時讀取。

使用方式：
    pip install google-genai
    export GEMINI_API_KEY=...                        # 取得 https://aistudio.google.com/apikey
    python scripts/generate_vocab.py --limit 20      # 先試 20 字
    python scripts/generate_vocab.py                 # 跑完整份詞表
    python scripts/generate_vocab.py --model pro     # 改用 Gemini 2.5 Pro 高品質

可重跑：已在 vocab_bank.json 內的字會自動略過；每批寫檔一次，中斷不會遺失既有進度。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WORDLIST = ROOT / "scripts" / "vocab_wordlist.txt"
BANK = ROOT / "vocab_bank.json"

MODELS = {"flash": "gemini-2.5-flash", "pro": "gemini-2.5-pro",
          "flash-lite": "gemini-2.5-flash-lite"}

# 與 ai.py 的 VOCAB_SYSTEM_PROMPT 同步；獨立一份方便本機離線跑。
SYSTEM_PROMPT = """你是台味日文單字記憶教練，擅長把日文聲音強行接到中文意思，並寫出母語人士日常口語例句。

# 輸出格式（嚴格）
只輸出一個 JSON array，前後不得有任何文字、不得包 markdown 程式碼區塊。
array 內每個物件對應一個輸入單字，順序與輸入相同，且必須含以下欄位：
- "word": 輸入單字原樣（日文漢字或假名headword）
- "kana": 假名讀音（平假名）
- "romaji": 羅馬拼音
- "meaning_zh": 繁體中文意思（精簡，1–2 詞組）
- "mnemonic": 台味諧音（繁中，4–10 字，把日文發音接到中文，生動好記，可荒謬搞笑）
- "image": 一句繁中（≤30 字），把諧音聲音對應到單字意思的具體畫面
- "example_jp": 一句口語自然的日本人例句（含漢字，≤20 字）
- "example_zh": example_jp 的繁中口語翻譯（自然，不死板）
- "usage_zh": 一句繁中，說明此字的使用時機與搭配
- "pos": 詞性的中文標籤，多詞性用 " / " 連起來
- "jlpt": 此字的 JLPT 級別，"N5"/"N4"/"N3"/"N2"/"N1" 擇一
"""


def load_bank() -> dict:
    if BANK.exists():
        try:
            return json.loads(BANK.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            print(f"⚠️  {BANK} 內容損毀，以空庫重來。", file=sys.stderr)
    return {}


def save_bank(bank: dict) -> None:
    BANK.write_text(json.dumps(bank, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_wordlist() -> list[dict]:
    """回傳 [{"word":..., "level":...}]；以「# Nx」區段標頭判定級別。"""
    if not WORDLIST.exists():
        sys.exit(f"找不到詞表：{WORDLIST}")
    out, seen, level = [], set(), ""
    for line in WORDLIST.read_text(encoding="utf-8").splitlines():
        s = line.strip()
        if not s:
            continue
        if s.startswith("#"):
            m = re.search(r"\b(N[1-5])\b", s)
            if m:
                level = m.group(1)
            continue
        if s not in seen:
            seen.add(s)
            out.append({"word": s, "level": level})
    return out


def chunked(seq: list, n: int):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def extract_json_array(text: str):
    text = (text or "").strip()
    m = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", text, re.DOTALL)
    if m:
        text = m.group(1)
    else:
        s, e = text.find("["), text.rfind("]")
        if s != -1 and e != -1 and e > s:
            text = text[s:e + 1]
    return json.loads(text)


def generate_batch(client, model: str, words: list[dict]):
    from google.genai import types
    items = "、".join(f"{w['word']}（{w['level']}）" for w in words)
    resp = client.models.generate_content(
        model=model,
        contents="請為以下日文單字生成資料：" + items,
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM_PROMPT,
            temperature=0.7,
            max_output_tokens=8000,
        ),
    )
    return extract_json_array(resp.text or "")


def main() -> None:
    parser = argparse.ArgumentParser(description="批次生成 vocab_bank.json (Gemini)")
    parser.add_argument("--limit", type=int, default=None, help="只跑前 N 個待補單字")
    parser.add_argument("--model", choices=list(MODELS), default="flash-lite")
    parser.add_argument("--batch-size", type=int, default=20)
    parser.add_argument("--retries", type=int, default=3)
    args = parser.parse_args()

    try:
        from google import genai
    except ImportError:
        sys.exit("請先安裝套件：pip install google-genai")

    api_key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
    if not api_key:
        sys.exit("請先設定環境變數：export GEMINI_API_KEY=... "
                 "(取得 https://aistudio.google.com/apikey)")

    client = genai.Client(api_key=api_key)
    bank = load_bank()
    words = load_wordlist()
    todo = [w for w in words if w["word"] not in bank]
    if args.limit:
        todo = todo[:args.limit]

    print(f"詞表 {len(words)} 字 | 已完成 {len(bank)} 字 | 待補 {len(todo)} 字 "
          f"| 模型 {MODELS[args.model]} | 批次 {args.batch_size}")
    if not todo:
        print("沒有待補單字。")
        return

    done = 0
    for batch in chunked(todo, args.batch_size):
        entries = None
        for attempt in range(args.retries):
            try:
                entries = generate_batch(client, MODELS[args.model], batch)
                break
            except Exception as e:  # noqa: BLE001
                wait = 2 ** attempt
                print(f"  retry {attempt + 1}/{args.retries} after {wait}s "
                      f"({type(e).__name__}: {e!s:.80})")
                time.sleep(wait)
        if entries is None:
            print(f"  ⚠️  跳過此批：{[w['word'] for w in batch]}")
            continue
        added = 0
        for e in entries:
            w = (e.get("word") or "").strip()
            if w and e.get("meaning_zh"):
                bank[w] = e
                added += 1
        save_bank(bank)
        done += len(batch)
        print(f"[{done}/{len(todo)}] +{added} 字寫入  |  目前庫存 {len(bank)} 字")

    print(f"完成。{BANK} 共 {len(bank)} 字。")


if __name__ == "__main__":
    main()
