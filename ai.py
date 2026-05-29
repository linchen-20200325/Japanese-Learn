# -*- coding: utf-8 -*-
"""ai.py — Gemini 互動層（情境生成、單字庫批次生成、GitHub 自動推回）。

設計沿用英文版 streamlit_app.py 的成熟做法，並改寫為日文 / JLPT 內容：
    • 多把 Gemini API key 自動輪轉（撞 429 換下一把）。
    • 四種模型 tier（Flash-Lite 額度最多，預設）。
    • 從 st.secrets / 環境變數讀 key 與 GitHub Token，防呆剝雜質。
    • vocab_bank.json 讀寫（含 st.cache_data 快取）與 GitHub Contents API 推回。

所有 prompt 一律要求繁體中文解說 + 日文教材，輸出嚴格 JSON / mermaid，方便程式解析。
"""

import json
import os
import re

import streamlit as st

VOCAB_BANK_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vocab_bank.json")
DEFAULT_REPO = "linchen-20200325/japanese-learn"


# ===========================================================================
# 模型 tier：免費 tier 每日請求數（RPD）由多到少
# ===========================================================================
_MODEL_MAP = {
    "Flash-Lite（推薦，免費 ~200/天）": "gemini-2.5-flash-lite",
    "2.0 Flash（舊版但額度多，~200/天）": "gemini-2.0-flash",
    "Flash（平衡，免費 ~20/天）": "gemini-2.5-flash",
    "Pro（最強，免費僅 ~5/天）": "gemini-2.5-pro",
}
GEN_MODEL_TIERS = list(_MODEL_MAP.keys())

# 短暫伺服器忙（秒級重試有用）
_TRANSIENT_HINTS = ("503", "UNAVAILABLE", "overloaded", "high demand", "DEADLINE_EXCEEDED")
# 配額耗盡（每日 free tier 上限，秒級重試無用，要換 key 或等隔天）
_QUOTA_HINTS = ("RESOURCE_EXHAUSTED", "429", "exceeded your current quota",
                "Resource has been exhausted")


# ===========================================================================
# 系統 Prompt（日文教材）
# ===========================================================================
GEN_SYSTEM_PROMPT = """# 角色
你是科學化日語學習專家、記憶法大師兼資料工程師。

# 理論依據
1. 雙碼理論：透過心智圖視覺化建立大腦基模。
2. 間隔重複（SRS）：透過 JSON 抽認卡固化長期記憶。
3. 詞塊教學法：學習母語人士的固定搭配「詞塊（chunks）」。
4. 關鍵字記憶法：透過荒謬搞笑的中文諧音或視覺圖像，把日文聲音與中文意義強行連結。

# 任務
根據使用者訊息提供的【目標情境與 JLPT 級別】，產出符合上述理論的實用日文對話教材。
語言風格須是日本人的日常自然對話，並貼合指定的 JLPT 級別難度（N5 最易、N1 最難）。

# 輸出限制（嚴格）
只輸出以下兩個程式碼區塊，前後與中間不得有任何開場白、結語或解釋文字。

## 區塊一：Mermaid flowchart 樹狀圖（日中雙語、嚴格語法）
用 ```mermaid 區塊製作一個 **`flowchart LR`** 樹狀圖（不要用 mindmap）。嚴格遵守以下語法，
任何違規都會讓畫面顯示「Syntax error in text」：

**規則**：
- 第一行固定：`flowchart LR`
- 每個節點用 `nodeId["顯示文字"]` 寫法，nodeId 只能是 ASCII 英數字（n0、n1、n0_0 ...）
- 節點文字務必用雙引號包起來
- **節點文字內絕對不可出現 `(` `)` `[` `]` `{` `}` 半形括號**（會被 mermaid 當形狀語法）。
  要表達括號請用全形 `（）` 或 `「」`
- 用 `-->` 連線
- 雙語用「日文 | 中文」分隔，例如 `n0_0["はじめまして | 初次見面"]`

**結構**：
- root 節點：`root(("情境名稱中文"))`（雙重圓括號是唯一允許的括號）
- 主分支 3-5 個，代表對話階段（開場、核心、收尾等），日文 ≤ 6 字 + 中文標籤
- 每分支底下 2-4 個子節點，日文短句 + 中文翻譯，用 `|` 分隔

**完整範例（請仿照產出，結構與標點都照抄）**：
```
flowchart LR
    root(("カフェで注文"))
    n0["挨拶 開場"]
    n1["注文 點餐"]
    n2["会計 結帳"]
    root --> n0
    root --> n1
    root --> n2
    n0_0["いらっしゃいませ | 歡迎光臨"]
    n0 --> n0_0
    n1_0["ホットコーヒーをください | 請給我熱咖啡"]
    n1 --> n1_0
    n2_0["カードで払えますか | 可以刷卡嗎"]
    n2 --> n2_0
```

## 區塊二：SRS 抽認卡與速記法
用 ```json 區塊輸出 3 到 5 張最具代表性的金句，須取自心智圖中出現的句子。
嚴格符合此結構（請確保 JSON 完全合法、可被 Python 讀取）：
{
  "flashcards": [
    {"id": 1, "sentence": "...", "kana": "...", "romaji": "...", "chinese": "...", "chunk": "...", "grammar": "...", "mnemonic": "...", "context": "..."}
  ]
}
- "id"：唯一流水號（整數）
- "sentence"：完整實用日文句子（含漢字）
- "kana"：整句的假名讀音（平假名）
- "romaji"：整句的羅馬拼音
- "chinese"：繁體中文自然翻譯
- "chunk"：該句中最核心的日本人常用詞塊
- "grammar"：該句的核心文法重點（繁中一句話說明文型）
- "mnemonic"：針對句中最關鍵單字的速記法，須是符合台灣人語感的搞笑中文諧音或視覺圖像，越荒謬越好
- "context"：一句繁體中文，說明在什麼具體情況下使用這句話
"""


VOCAB_SYSTEM_PROMPT = """你是台味日文單字記憶教練，擅長把日文聲音強行接到中文意思，並寫出母語人士日常口語例句。

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
- "usage_zh": 一句繁中，說明此字的使用時機與搭配（常見句型、語感、正式或口語）
- "pos": 詞性的中文標籤，例如 "名詞"、"動詞"、"形容詞"、"副詞"、"助詞"。多詞性用 " / " 連起來
- "jlpt": 此字的 JLPT 級別，"N5"/"N4"/"N3"/"N2"/"N1" 擇一

# 品質規範
- 諧音要鮮明、好記，避免敷衍。
- 例句要像真實對話，不要教科書日文。
- 用法要點出常見搭配或語境差異。

# 輸出範例（單字 "約束"）
[{"word":"約束","kana":"やくそく","romaji":"yakusoku","meaning_zh":"約定、承諾","mnemonic":"鴨嗽哭","image":"你跟『鴨』子約定，牠『嗽』了還『哭』，逼牠遵守約定。","example_jp":"友達と会う約束をしました。","example_zh":"我和朋友約好要見面。","usage_zh":"「約束を守る」表示遵守約定，「約束を破る」表示違背約定，日常與正式皆常用。","pos":"名詞 / 動詞","jlpt":"N4"}]
"""


READING_GEN_PROMPT = """你是日文閱讀教材編輯。使用者給「主題 + JLPT 級別」，你產出一篇可互動的閱讀練習。

# 嚴格輸出 JSON（只輸出 JSON，前後不得有任何文字、不得包 markdown code fence）
{
  "id": "topic-keyword-id",
  "title": "日文標題",
  "title_zh": "繁中標題",
  "level": "N5 / N4 / N3 / N2 / N1 擇一",
  "summary": "繁中一句話描述文章特色與適用文法",
  "sentences": [
    {
      "jp": "自然口語/書面日文（含漢字），≤ 30 字/句",
      "kana": "整句假名讀音",
      "zh": "繁中翻譯",
      "vocab": {"単語": "中文翻譯", "別の語": "..."},
      "grammar": "該句核心文法重點（繁中一句話）"
    }
  ]
}

# 數量規範
- sentences: 5-7 句
- 每句 vocab 4-8 個詞（挑學習者最可能不懂的，key 用日文原詞）

# 級別差異
- N5: 50 音、基礎問候、生活單字、現在/過去式
- N4: 日常會話、て形、可能形、授受動詞
- N3: 複雜句型、抽象語彙、被動使役
- N2: 書面語、商務日文、接續詞
- N1: 慣用句、正式文書、高階語彙
"""


# ===========================================================================
# Secret / key 讀取與清潔
# ===========================================================================
def _read_secret(name: str):
    try:
        if name in st.secrets:
            return st.secrets[name]
    except Exception:
        pass
    return os.environ.get(name)


def _secret_names() -> list:
    try:
        return list(st.secrets.keys())
    except Exception:
        return []


def _clean_keys(v) -> list:
    """從任何輸入抽出所有 AIza 開頭、長度 ≥ 30 的合法 Gemini key，去重保序。"""
    import unicodedata as _ud
    if v is None:
        return []
    if isinstance(v, (list, tuple)):
        out = []
        for item in v:
            for k in _clean_keys(item):
                if k not in out:
                    out.append(k)
        return out
    if isinstance(v, dict):
        out = []
        for item in v.values():
            for k in _clean_keys(item):
                if k not in out:
                    out.append(k)
        return out
    s = str(v).replace("\n", " ").replace("\r", " ").replace("\t", " ")
    s = "".join(c for c in s if _ud.category(c)[0] not in ("C", "M") or c == " ")
    s = s.strip()
    while len(s) >= 2 and s[0] == s[-1] and s[0] in ('"', "'", "`"):
        s = s[1:-1].strip()
    chunks = re.split(r"[,;\n\r\t=\s]+", s)
    out = []
    for c in chunks:
        c = c.strip().strip('"').strip("'").strip("`")
        if c.startswith("AIza") and len(c) >= 30 and c not in out:
            out.append(c)
    if not out and s.startswith("AIza") and len(s) >= 30:
        out.append(s)
    return out


def get_all_api_keys() -> list:
    """讀所有 Gemini key（標準名稱優先，再掃含 GEMINI/GOOGLE 的 secret/env）。"""
    keys = []
    seen = set()

    def _push(v):
        for k in _clean_keys(v):
            if k not in seen:
                seen.add(k)
                keys.append(k)

    for name in ("GEMINI_API_KEY", "GOOGLE_API_KEY", "GEMINI_KEY",
                 "GOOGLE_GENAI_API_KEY", "GEMINI_API_KEYS"):
        _push(_read_secret(name))
    for name in _secret_names():
        upper = name.upper()
        if ("GEMINI" in upper or "GOOGLE" in upper) and "API" in upper:
            _push(_read_secret(name))
    for name, val in os.environ.items():
        upper = name.upper()
        if val and ("GEMINI" in upper or "GOOGLE" in upper) and "API" in upper:
            _push(val)
    return keys


def get_api_key():
    """回傳第一把可用 key（優先未在 session 標記為耗盡的）。"""
    all_keys = get_all_api_keys()
    if not all_keys:
        return None
    try:
        exhausted = st.session_state.get("_exhausted_keys", set())
    except Exception:
        exhausted = set()
    fresh = [k for k in all_keys if k not in exhausted]
    return fresh[0] if fresh else all_keys[0]


def get_github_token():
    """讀 GitHub PAT，用於自動把 vocab_bank.json commit 回 repo。"""
    raw = (_read_secret("GITHUB_TOKEN") or _read_secret("GH_TOKEN")
           or _read_secret("GITHUB_PAT"))
    if not raw:
        return None
    import unicodedata as _ud
    s = str(raw).replace("\n", " ").replace("\r", " ").replace("\t", " ")
    s = "".join(c for c in s if _ud.category(c)[0] not in ("C", "M") or c == " ")
    s = s.strip()
    while len(s) >= 2 and s[0] == s[-1] and s[0] in ('"', "'", "`"):
        s = s[1:-1].strip()
    return s or None


# ===========================================================================
# LLM 生成（多 key 輪轉）
# ===========================================================================
def _llm_generate(system_prompt: str, user_msg: str, tier: str,
                  max_tokens: int = 2000, retries: int = 3) -> str:
    """單次生成。撞 429 自動換下一把 key 並標記耗盡；503 走秒級退避重試。"""
    import time

    all_keys = get_all_api_keys()
    if not all_keys:
        raise RuntimeError("尚未設定 GEMINI_API_KEY")
    try:
        exhausted = st.session_state.setdefault("_exhausted_keys", set())
    except Exception:
        exhausted = set()
    fresh_keys = [k for k in all_keys if k not in exhausted] or list(all_keys)

    model_id = _MODEL_MAP.get(tier) or next(iter(_MODEL_MAP.values()))

    from google import genai
    from google.genai import types

    last_err = None
    for key in fresh_keys:
        for attempt in range(retries):
            try:
                client = genai.Client(api_key=key)
                resp = client.models.generate_content(
                    model=model_id,
                    contents=user_msg,
                    config=types.GenerateContentConfig(
                        system_instruction=system_prompt,
                        temperature=0.7,
                        max_output_tokens=max_tokens,
                    ),
                )
                return resp.text or ""
            except Exception as e:  # noqa: BLE001
                last_err = e
                em = str(e)
                if any(h in em for h in _QUOTA_HINTS):
                    exhausted.add(key)
                    break
                if attempt < retries - 1 and any(h in em for h in _TRANSIENT_HINTS):
                    time.sleep(2 ** attempt)
                    continue
                raise
    if last_err:
        raise last_err
    return ""


def generate_material(scenario: str, level: str, tier: str) -> str:
    return _llm_generate(
        GEN_SYSTEM_PROMPT,
        f"情境：{scenario}\nJLPT 級別：{level}",
        tier, max_tokens=2200,
    )


def gen_reading(topic: str, level: str, tier: str) -> dict:
    """呼叫 Gemini 產出一篇可互動日文閱讀。"""
    text = _llm_generate(READING_GEN_PROMPT, f"主題：{topic}\n級別：{level}",
                         tier, max_tokens=6000)
    m = re.search(r"\{[\s\S]*\}", text)
    if not m:
        raise RuntimeError(f"Gemini 回應內無 JSON：{text[:200]}")
    return json.loads(m.group(0))


# ===========================================================================
# 解析 mermaid / flashcards
# ===========================================================================
def _sanitize_mermaid(text: str) -> str:
    """清潔 mermaid：把節點 ["..."] 內半形括號改全形；mindmap 開頭改 flowchart LR。"""
    if not text:
        return text
    lines = text.splitlines()
    if lines and lines[0].strip().lower().startswith("mindmap"):
        lines[0] = "flowchart LR"

    def _clean_label(m):
        inner = m.group(1)
        inner = (inner.replace("(", "（").replace(")", "）")
                      .replace("[", "「").replace("]", "」")
                      .replace("{", "「").replace("}", "」"))
        return f'["{inner}"]'

    cleaned = []
    for ln in lines:
        ln = re.sub(r'\["([^"]*)"\]', _clean_label, ln)
        cleaned.append(ln)
    return "\n".join(cleaned)


def parse_blocks(text: str):
    """從回應抽出 mermaid 圖與 flashcards JSON。"""
    mermaid = None
    cards = None
    m = re.search(r"```mermaid\s*(.*?)```", text, re.DOTALL)
    if m:
        mermaid = _sanitize_mermaid(m.group(1).strip())
    j = re.search(r"```json\s*(.*?)```", text, re.DOTALL)
    if j:
        try:
            cards = json.loads(j.group(1).strip()).get("flashcards")
        except (json.JSONDecodeError, AttributeError):
            cards = None
    return mermaid, cards


def extract_json_array(text: str):
    """從模型回應抽出 JSON array，容忍程式碼圍欄或前後雜訊。"""
    text = (text or "").strip()
    m = re.search(r"```(?:json)?\s*(\[.*?\])\s*```", text, re.DOTALL)
    if m:
        text = m.group(1)
    else:
        s, e = text.find("["), text.rfind("]")
        if s != -1 and e != -1 and e > s:
            text = text[s:e + 1]
    return json.loads(text)


# ===========================================================================
# vocab_bank.json 讀寫
# ===========================================================================
@st.cache_data(show_spinner=False)
def _load_vocab_bank_cached(_mtime: float) -> dict:
    """讀取 + 清理：丟掉缺 meaning_zh 的不完整 entry。"""
    try:
        with open(VOCAB_BANK_FILE, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}
    cleaned = {}
    for k, v in (raw or {}).items():
        kk = (k or "").strip()
        if not kk or kk in cleaned:
            continue
        if not isinstance(v, dict) or not v.get("meaning_zh"):
            continue
        v["word"] = kk
        cleaned[kk] = v
    return cleaned


def load_vocab_bank() -> dict:
    """讀取 vocab_bank.json；以檔案 mtime 當 cache key，檔案變動自動失效。"""
    try:
        mtime = os.path.getmtime(VOCAB_BANK_FILE)
    except OSError:
        mtime = 0.0
    return _load_vocab_bank_cached(mtime)


def generate_vocab_batch(words: list, tier: str) -> list:
    """呼叫 Gemini 一次生成一批日文單字的 JSON 資料。words 為 [(word, level), ...] 或 [word]。"""
    items = []
    for w in words:
        if isinstance(w, (list, tuple)):
            items.append(f"{w[0]}（{w[1]}）")
        elif isinstance(w, dict):
            items.append(f"{w['word']}（{w.get('level', '')}）")
        else:
            items.append(str(w))
    text = _llm_generate(VOCAB_SYSTEM_PROMPT,
                         "請為以下日文單字生成資料：" + "、".join(items),
                         tier, max_tokens=8000)
    return extract_json_array(text)


def push_bank_to_github(merged: dict, silent: bool = False):
    """把合併後的 vocab_bank 透過 GitHub Contents API 推回 repo。回傳 (ok, info)。"""
    import base64
    import urllib.error
    import urllib.request

    token = get_github_token()
    if not token:
        return False, {"stage": "token", "msg": "未設定 GITHUB_TOKEN secret"}

    repo = _read_secret("GITHUB_REPO") or DEFAULT_REPO
    branch = _read_secret("GITHUB_BRANCH") or "main"
    path = "vocab_bank.json"
    payload_json = json.dumps(merged, ensure_ascii=False, indent=2) + "\n"

    api = f"https://api.github.com/repos/{repo}/contents/{path}"
    headers = {"Authorization": f"Bearer {token}",
               "Accept": "application/vnd.github+json",
               "User-Agent": "japanese-learn-cloud",
               "X-GitHub-Api-Version": "2022-11-28"}

    try:
        req = urllib.request.Request(f"{api}?ref={branch}", headers=headers)
        with urllib.request.urlopen(req, timeout=15) as r:
            sha = json.loads(r.read())["sha"]
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:600]
        return False, {"stage": "GET sha", "code": e.code, "body": body,
                       "repo": repo, "branch": branch}
    except Exception as e:  # noqa: BLE001
        return False, {"stage": "GET sha", "code": 0, "body": f"{type(e).__name__}: {e}"}

    try:
        body = json.dumps({
            "message": f"vocab_bank: cloud append（共 {len(merged)} 字）",
            "content": base64.b64encode(payload_json.encode("utf-8")).decode("ascii"),
            "sha": sha,
            "branch": branch,
        }).encode("utf-8")
        req2 = urllib.request.Request(api, data=body, method="PUT",
                                      headers={**headers, "Content-Type": "application/json"})
        with urllib.request.urlopen(req2, timeout=20) as r:
            result = json.loads(r.read())
        commit_sha = result.get("commit", {}).get("sha", "")[:7]
        return True, {"commit": commit_sha, "repo": repo, "branch": branch}
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:600]
        return False, {"stage": "PUT", "code": e.code, "body": body,
                       "repo": repo, "branch": branch}
    except Exception as e:  # noqa: BLE001
        return False, {"stage": "PUT", "code": 0, "body": f"{type(e).__name__}: {e}"}
