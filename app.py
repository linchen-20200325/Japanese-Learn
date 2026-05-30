# -*- coding: utf-8 -*-
"""
app.py — JLPT 全階段日文學習 App（N1 ~ N5）

特色：
    • Sidebar 兩層導覽：先選級別，再切換功能。
    • 50 音僅在「N5 基礎」顯示，其餘級別自動隱藏，保持介面乾淨。
    • 單字／例句「選到才顯示」中文與唸法（假名），搭配使用說明與例句。
    • 文法解說含意義、用法與多組例句；情境短文／文章可逐句顯示唸法與中文。
    • 每個級別擁有獨立的學習進度（st.session_state 不互相覆蓋）。
    • gTTS 採記憶體級播放（BytesIO），避免實體檔案鎖定（File Lock）。

執行方式：
    pip install -r requirements.txt
    streamlit run app.py
"""

import json
import os
import random
from datetime import date, timedelta
from io import BytesIO

import streamlit as st
import streamlit.components.v1 as components

import ai
import data

# gTTS 為選用相依套件；若未安裝則優雅降級（停用語音，不中斷程式）。
try:
    from gtts import gTTS

    _GTTS_AVAILABLE = True
except Exception:  # pragma: no cover - 環境無網路 / 未安裝
    _GTTS_AVAILABLE = False

# 複習卡與已存情境課程持久化（重整／重啟仍保留）；Cloud 為暫存檔，重新部署會重置。
DATA_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "dashboard_data.json")


def today_str() -> str:
    return date.today().isoformat()


def load_data() -> dict:
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                d = json.load(f)
            d.setdefault("review_cards", [])
            d.setdefault("lessons", [])
            return d
        except (json.JSONDecodeError, OSError):
            pass
    return {"review_cards": [], "lessons": []}


def save_data() -> None:
    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(st.session_state.app_data, f, ensure_ascii=False, indent=2)
    except OSError:
        pass


# ===========================================================================
# 語音引擎（記憶體級，避免 File Lock）
# ===========================================================================
@st.cache_data(show_spinner=False)
def synthesize_speech(text: str) -> bytes:
    """
    將日文文字合成為 MP3 位元組串。

    完全在記憶體中操作（BytesIO），不寫入磁碟，
    因此不會產生暫存檔案，也不會發生檔案鎖定問題。
    結果以 st.cache_data 快取，重複播放同一文字不需重新合成。
    """
    buffer = BytesIO()
    tts = gTTS(text=text, lang="ja")
    tts.write_to_fp(buffer)
    buffer.seek(0)
    return buffer.getvalue()


def play_button(text: str, key: str, label: str = "🔊 發音") -> None:
    """渲染一個發音按鈕；按下後於記憶體中合成並播放。"""
    if not _GTTS_AVAILABLE:
        st.caption("🔇 語音功能需安裝 gTTS 並連線網路")
        return

    if st.button(label, key=key):
        try:
            audio_bytes = synthesize_speech(text)
            st.audio(audio_bytes, format="audio/mp3")
        except Exception as exc:  # 網路或服務暫時不可用
            st.warning(f"語音合成失敗（請檢查網路）：{exc}")


def render_examples(examples: list, key_prefix: str) -> None:
    """渲染例句清單：日文 + 唸法 + 中文 + 發音。"""
    if not examples:
        return
    st.markdown("**例句：**")
    for i, ex in enumerate(examples):
        with st.container(border=True):
            st.markdown(f"🇯🇵 {ex['jp']}")
            st.caption(f"📖 唸法：{ex.get('kana', '')}")
            st.caption(f"🇹🇼 {ex.get('zh', '')}")
            play_button(ex["jp"], key=f"{key_prefix}_ex_{i}", label="🔊 播放例句")


# ===========================================================================
# Session State：各級別獨立進度
# ===========================================================================
def init_state() -> None:
    """初始化各級別獨立的學習進度容器（僅執行一次）。"""
    if "progress" not in st.session_state:
        # 每個級別獨立記錄已學會的單字（以 kanji 作為唯一鍵）
        st.session_state.progress = {lv: set() for lv in data.LEVEL_ORDER}
    if "quiz" not in st.session_state:
        # 每個級別獨立的測驗統計
        st.session_state.quiz = {
            lv: {"correct": 0, "total": 0} for lv in data.LEVEL_ORDER
        }
    if "app_data" not in st.session_state:
        # 複習卡與已存課程（全級別共用，持久化於 dashboard_data.json）
        st.session_state.app_data = load_data()


def mark_learned(level: str, kanji: str) -> None:
    """將某單字標記為已學會（記錄於該級別）。"""
    st.session_state.progress[level].add(kanji)


def learned_count(level: str) -> int:
    return len(st.session_state.progress[level])


# ===========================================================================
# 各功能頁面
# ===========================================================================
def _to_katakana(s: str) -> str:
    """把平假名字串轉成片假名（逐字 Unicode 偏移 +0x60；非平假名原樣保留）。"""
    return "".join(
        chr(ord(c) + 0x60) if "ぁ" <= c <= "ゖ" else c for c in s
    )


def _level_items(file_items: list, sess_key: str, level, key_field: str) -> list:
    """合併「部署檔 + 本 session 生成」並去重（Cloud 唯讀寫不進本機，故顯示一律疊上 session）。"""
    sess = st.session_state.get(sess_key, [])
    out, seen = [], set()
    for it in list(file_items) + list(sess):
        if level is not None and it.get("level") != level:
            continue
        k = it.get(key_field) or it.get("title") or it.get("point")
        if k in seen:
            continue
        seen.add(k)
        out.append(it)
    return out


def page_gojuon(level: str) -> None:
    """50 音（基礎，僅 N5）：可切換平假名／片假名。"""
    st.header("🈁 50 音入門")
    st.write("日文的基礎發音表，建議先熟練清音，再進入濁音、半濁音與拗音。")

    script = st.radio("文字種類", ["平假名", "片假名"], horizontal=True, key="goj_script")
    is_kata = script == "片假名"
    st.caption("片假名多用於外來語、擬聲擬態與強調；發音與平假名相同。"
               if is_kata else "平假名是日文最基礎的音節文字。")

    gojuon = data.load_gojuon()
    sections = [
        ("清音", "seion"),
        ("濁音", "dakuon"),
        ("半濁音", "handakuon"),
        ("拗音", "yoon"),
    ]

    tabs = st.tabs([name for name, _ in sections])
    for tab, (name, key) in zip(tabs, sections):
        with tab:
            rows = gojuon.get(key, [])
            cols_per_row = 5
            for i in range(0, len(rows), cols_per_row):
                cols = st.columns(cols_per_row)
                for j, (col, item) in enumerate(zip(cols, rows[i : i + cols_per_row])):
                    with col:
                        kana = _to_katakana(item["kana"]) if is_kata else item["kana"]
                        st.markdown(
                            f"<div style='text-align:center;font-size:2rem;"
                            f"line-height:1.2'>{kana}</div>"
                            f"<div style='text-align:center;color:#888'>"
                            f"{item['romaji']}</div>",
                            unsafe_allow_html=True,
                        )
                        # 用 (區段, 位置索引) 當 key，避免 じ/ぢ、ず/づ 同 romaji 撞 key
                        play_button(item["kana"], key=f"goj_{key}_{i + j}_{item['romaji']}")


def page_vocab(level: str) -> None:
    """核心單字庫（依級別動態切換）。"""
    st.header(f"📚 {data.LEVELS[level]['label']} 核心單字庫")
    st.caption("點開「顯示中文與唸法」即可看到中文翻譯、假名唸法、使用方式與例句。")

    vocab = data.load_vocab(level)
    if not vocab:
        st.info("此級別尚無單字資料。")
        return

    learned = st.session_state.progress[level]
    st.progress(
        learned_count(level) / len(vocab) if vocab else 0,
        text=f"本級別已學會 {learned_count(level)} / {len(vocab)} 個單字",
    )

    for idx, word in enumerate(vocab):
        done = word["kanji"] in learned
        with st.container(border=True):
            head, btn = st.columns([4, 1])
            with head:
                # 預設只顯示漢字（與詞性），中文與唸法需「選到才跑出來」
                st.subheader(f"{word['kanji']}　{'✅' if done else ''}")
                if word.get("pos"):
                    st.caption(f"詞性：{word['pos']}")
            with btn:
                play_button(word["kanji"], key=f"vocab_play_{level}_{idx}")
                if st.button(
                    "已學會" if not done else "↩️ 取消",
                    key=f"learn_{level}_{idx}",
                ):
                    if done:
                        learned.discard(word["kanji"])
                    else:
                        mark_learned(level, word["kanji"])
                    st.rerun()

            with st.expander("👀 顯示中文與唸法"):
                st.markdown(
                    f"**唸法（假名）：** {word['kana']}　|　"
                    f"**羅馬拼音：** {word['romaji']}"
                )
                st.markdown(f"**中文：** {word['chinese']}")
                if word.get("grammar"):
                    st.info(f"📝 核心文法：{word['grammar']}")
                if word.get("usage"):
                    st.success(f"💡 怎麼用：{word['usage']}")
                render_examples(word.get("examples", []), key_prefix=f"vocab_{level}_{idx}")


def _persist_grammar(items: list, level: str) -> tuple:
    """把 AI 生成的文法加入永久庫：session 疊加層（立即可見）+ 推回 GitHub。"""
    for it in items:
        it.setdefault("level", level)
    st.session_state.setdefault("_sess_grammar", []).extend(items)  # 立即可見
    bank = list(ai.load_grammar_bank())
    have = {(g.get("level"), g.get("point")) for g in bank}
    added = 0
    for it in items:
        it.setdefault("level", level)
        if (it.get("level"), it.get("point")) in have:
            continue
        bank.append(it)
        have.add((it.get("level"), it.get("point")))
        added += 1
    payload = json.dumps(bank, ensure_ascii=False, indent=2) + "\n"
    try:
        with open(ai.GRAMMAR_BANK_FILE, "w", encoding="utf-8") as f:
            f.write(payload)
    except OSError:
        pass
    for fn in (ai.load_grammar_bank, ai._load_grammar_bank_cached):
        if hasattr(fn, "clear"):
            fn.clear()
    ok, info = ai.github_put_file(
        "grammar_bank.json", payload,
        f"grammar_bank: AI 生成 {level} 文法 +{added}（共 {len(bank)} 條）")
    return ok, added


def _render_grammar_item(g: dict, level: str, key_prefix: str, expanded: bool = False) -> None:
    with st.expander(f"{g['point']}　—　{g['meaning']}", expanded=expanded):
        st.markdown(f"**意義：** {g['meaning']}")
        if g.get("usage"):
            st.success(f"💡 用法：{g['usage']}")
        render_examples(g.get("examples", []), key_prefix=key_prefix)


def page_grammar(level: str) -> None:
    """文法解說核心（依級別動態切換）＋ AI 生成不重複新文法擴充資料庫。"""
    st.header(f"📖 {data.LEVELS[level]['label']} 文法解說核心")
    st.caption("每個文法皆含意義、用法說明與多組例句（可顯示唸法與中文）。")

    db_grammar = data.load_grammar(level)
    bank_grammar = _level_items(ai.load_grammar_bank(), "_sess_grammar", level, "point")

    # 🤖 AI 生成新文法（不重複，擴充資料庫）
    if st.session_state.pop("_gram_saved", None) is not None:
        st.success(f"已生成並存進文法資料庫！本級別現有 {len(db_grammar) + len(bank_grammar)} 條。")
    with st.expander("🤖 AI 生成不同程度、不重複的新文法（擴充資料庫）", expanded=False):
        if not ai.get_api_key():
            st.warning("需要 Gemini 金鑰才能生成。請至側欄或 Cloud Secrets 設定 `GEMINI_API_KEY`。")
        else:
            c1, c2 = st.columns([2, 3])
            n = c1.number_input("一次生成幾條", 1, 10, 3, key=f"gramn_{level}")
            if c2.button("🤖 生成新文法", type="primary", use_container_width=True,
                         key=f"gramgen_{level}"):
                existing = [g["point"] for g in db_grammar + bank_grammar]
                try:
                    with st.spinner("AI 生成中…"):
                        items = ai.gen_grammar_batch(level, existing, int(n),
                                                     next(iter(ai.GEN_MODEL_TIERS)))
                    if items:
                        ok, added = _persist_grammar(items, level)
                        st.session_state["_gram_saved"] = added
                        st.rerun()
                    else:
                        st.warning("這次沒有產生新的（可能與既有重複），請再試一次。")
                except Exception as e:  # noqa: BLE001
                    st.error(_friendly_gen_error(str(e)))

    if not db_grammar and not bank_grammar:
        st.info("此級別尚無文法資料。可用上方「AI 生成新文法」建立。")
        return

    for idx, g in enumerate(db_grammar):
        _render_grammar_item(g, level, f"gram_{level}_{idx}", expanded=(idx == 0))

    if bank_grammar:
        st.markdown(f"#### 🤖 AI 擴充文法（{len(bank_grammar)} 條，持續累積）")
        for idx, g in enumerate(bank_grammar):
            _render_grammar_item(g, level, f"grambank_{level}_{idx}")


def page_passage(level: str) -> None:
    """情境短文與進級（多篇短文／文章 + 小測驗，依級別動態切換）。"""
    st.header(f"📝 {data.LEVELS[level]['label']} 情境短文與進級")

    passages = data.load_passages(level)
    if not passages:
        st.info("此級別尚無短文資料。")
        return

    titles = [f"{p.get('type', '短文')}｜{p['title']}" for p in passages]
    choice = st.radio("選擇一篇閱讀：", titles, key=f"passage_pick_{level}")
    passage = passages[titles.index(choice)]

    st.subheader(f"{passage.get('type', '短文')}：{passage['title']}")

    # 整篇朗讀
    full_text = "".join(s["jp"] for s in passage.get("sentences", []))
    play_button(full_text, key=f"passage_full_{level}", label="🔊 整篇朗讀")

    show_all = st.toggle("顯示全文唸法與中文", key=f"passage_showall_{level}")

    for i, sent in enumerate(passage.get("sentences", [])):
        with st.container(border=True):
            st.markdown(f"### {sent['jp']}")
            cols = st.columns([1, 3])
            with cols[0]:
                play_button(sent["jp"], key=f"passage_{level}_{i}", label="🔊 播放")
            if show_all:
                st.caption(f"📖 唸法：{sent.get('kana', '')}")
                st.caption(f"🇹🇼 {sent.get('zh', '')}")
            else:
                with st.expander("顯示唸法與中文"):
                    st.caption(f"📖 唸法：{sent.get('kana', '')}")
                    st.caption(f"🇹🇼 {sent.get('zh', '')}")

    st.divider()
    _vocab_quiz(level)


def _vocab_quiz(level: str) -> None:
    """以本級別單字產生「中翻日（選假名）」小測驗。"""
    st.subheader("🎯 進級小測驗")
    vocab = data.load_vocab(level)
    if len(vocab) < 2:
        st.info("單字不足，無法產生測驗。")
        return

    quiz_key = f"current_quiz_{level}"
    # 為每個級別維持一題當前題目，切換級別不互相干擾。
    if quiz_key not in st.session_state:
        st.session_state[quiz_key] = _new_question(vocab)

    q = st.session_state[quiz_key]
    st.write(f"請問「**{q['prompt']}**」的正確唸法（假名）是？")

    choice = st.radio(
        "選擇答案：",
        q["options"],
        key=f"quiz_choice_{level}_{q['nonce']}",
        index=None,
    )

    col_submit, col_next = st.columns(2)
    with col_submit:
        if st.button("送出答案", key=f"submit_{level}_{q['nonce']}"):
            stats = st.session_state.quiz[level]
            stats["total"] += 1
            if choice == q["answer"]:
                stats["correct"] += 1
                st.success("正解！🎉")
            else:
                st.error(f"再加油！正確答案是：{q['answer']}")
    with col_next:
        if st.button("下一題 ➡️", key=f"next_{level}_{q['nonce']}"):
            st.session_state[quiz_key] = _new_question(vocab)
            st.rerun()

    stats = st.session_state.quiz[level]
    if stats["total"]:
        st.caption(
            f"本級別測驗紀錄：答對 {stats['correct']} / {stats['total']} 題"
            f"（正確率 {stats['correct'] / stats['total']:.0%}）"
        )


def _new_question(vocab: list) -> dict:
    """產生一道測驗題（中文 → 選假名）。"""
    target = random.choice(vocab)
    distractors = [w for w in vocab if w["kanji"] != target["kanji"]]
    sample = random.sample(distractors, k=min(3, len(distractors)))
    options = [target["kana"]] + [w["kana"] for w in sample]
    random.shuffle(options)
    return {
        "prompt": target["chinese"],
        "answer": target["kana"],
        "options": options,
        "nonce": random.randint(0, 10**9),
    }


# ===========================================================================
# 複習（SRS）— 全級別共用的句卡複習池（SM-2 簡化版）
# ===========================================================================
def add_cards_to_review(cards: list) -> int:
    """把句卡複製進複習清單並掛上 SM-2 排程欄位；以 sentence 去重。回傳新增數。"""
    deck = st.session_state.app_data.setdefault("review_cards", [])
    existing = {c.get("sentence") for c in deck}
    next_id = max((c.get("id", 0) for c in deck), default=0) + 1
    added = 0
    for c in cards:
        sent = c.get("sentence")
        if not sent or sent in existing:
            continue
        rc = dict(c)
        rc.update(id=next_id, interval=0, ease=2.5, reps=0, due=today_str())
        deck.append(rc)
        existing.add(sent)
        next_id += 1
        added += 1
    if added:
        save_data()
    return added


def schedule_card(card: dict, grade: str) -> None:
    """SM-2 簡化版：grade 為 again / good / easy，就地更新排程。"""
    ease = card.get("ease", 2.5)
    reps = card.get("reps", 0)
    interval = card.get("interval", 0)
    if grade == "again":
        reps, interval = 0, 1
        ease = max(1.3, ease - 0.2)
    else:
        if reps == 0:
            interval = 1 if grade == "good" else 2
        elif reps == 1:
            interval = 3 if grade == "good" else 5
        else:
            interval = max(1, round(interval * (ease if grade == "good" else ease * 1.3)))
        reps += 1
        if grade == "easy":
            ease += 0.15
    card.update(ease=round(ease, 2), reps=reps, interval=interval,
                due=(date.today() + timedelta(days=interval)).isoformat(),
                last=today_str())


def due_count() -> int:
    today = today_str()
    return sum(1 for c in st.session_state.app_data.get("review_cards", [])
               if c.get("due", today) <= today)


# ===========================================================================
# 科學學習監督：依間隔重複(SRS)狀態分析記憶強度
# ===========================================================================
def card_mastery(card: dict) -> str:
    """依複習次數與間隔判斷記憶強度：new / learning / young / mature。"""
    if card.get("reps", 0) == 0:
        return "new"
    interval = card.get("interval", 0)
    if interval >= 21:
        return "mature"
    if interval >= 7:
        return "young"
    return "learning"


def mastery_distribution() -> dict:
    """統計複習牌組各記憶強度的卡片數。"""
    dist = {"new": 0, "learning": 0, "young": 0, "mature": 0}
    for c in st.session_state.app_data.get("review_cards", []):
        dist[card_mastery(c)] = dist.get(card_mastery(c), 0) + 1
    return dist


def review_forecast(days: int = 7) -> dict:
    """未來 days 天每天到期的卡片數（逾期算今天），供複習負擔預測。"""
    today = date.today()
    labels = [(today + timedelta(days=i)).strftime("%m/%d") for i in range(days)]
    counts = dict.fromkeys(labels, 0)
    for c in st.session_state.app_data.get("review_cards", []):
        try:
            due = date.fromisoformat(c.get("due", today_str()))
        except ValueError:
            continue
        delta = (due - today).days
        if delta < 0:
            counts[labels[0]] += 1
        elif delta < days:
            counts[labels[delta]] += 1
    return counts


# ===========================================================================
# Mermaid 心智圖渲染
# ===========================================================================
_MERMAID_HTML = """
<div class="mermaid">__CODE__</div>
<script type="module">
  import mermaid from 'https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs';
  mermaid.initialize({ startOnLoad: true, securityLevel: 'loose' });
</script>
"""


def render_mermaid(code: str, height: int = 420) -> None:
    html = _MERMAID_HTML.replace("__CODE__", code)
    if hasattr(st, "iframe"):  # Streamlit ≥ 1.57
        st.iframe(html, height=height)
    else:
        components.html(html, height=height, scrolling=True)


def render_sentence_cards(cards: list, key_prefix: str) -> None:
    """渲染 AI 句卡（日文 + 假名 + 羅馬拼音 + 中文 + 文法 + 諧音），每張附 gTTS 發音。"""
    for i, c in enumerate(cards):
        with st.container(border=True):
            st.markdown(f"### {c.get('sentence', '')}")
            bits = []
            if c.get("kana"):
                bits.append(f"假名 `{c['kana']}`")
            if c.get("romaji"):
                bits.append(f"羅馬 `{c['romaji']}`")
            if bits:
                st.caption("　".join(bits))
            if c.get("chinese"):
                st.markdown(f"🇹🇼 {c['chinese']}")
            if c.get("chunk"):
                st.markdown(f"🧩 詞塊：`{c['chunk']}`")
            if c.get("grammar"):
                st.markdown(f"📝 文法：{c['grammar']}")
            if c.get("mnemonic"):
                st.markdown(f"🤯 速記：{c['mnemonic']}")
            if c.get("context"):
                st.caption(f"💡 {c['context']}")
            if c.get("sentence"):
                play_button(c["sentence"], key=f"{key_prefix}_play_{i}")


# ===========================================================================
# 🃏 單字卡（翻面學習，含 gTTS 發音與台味諧音）
# ===========================================================================
def page_flashcards(level: str) -> None:
    st.header(f"🃏 {data.LEVELS[level]['label']} 單字卡")
    with st.expander("💡 這是什麼？怎麼用？", expanded=False):
        st.markdown(
            "**單字卡**＝翻面學習區。正面看日文 + 假名 + 羅馬拼音 + 台味諧音並聽發音，"
            "心裡先想中文意思，再「🔄 翻面」對答案；背面有中文、例句、文法／用法。\n\n"
            "deck 自動合併本級別**核心單字**與「📖 單字庫」中同級別的字。"
        )

    bank = ai.load_vocab_bank()
    live = st.session_state.get("live_bank", {})
    synced = st.session_state.get("synced_bank", {})
    full_bank = {**bank, **synced, **live}

    deck = []
    for w in data.load_vocab(level):
        ex = (w.get("examples") or [{}])[0]
        deck.append({"word": w["kanji"], "kana": w["kana"], "romaji": w["romaji"],
                     "meaning_zh": w["chinese"], "usage_zh": w.get("usage") or w.get("grammar", ""),
                     "pos": w.get("pos", ""),
                     "example_jp": ex.get("jp", ""), "example_zh": ex.get("zh", ""),
                     "src": "core"})
    have = {d["word"] for d in deck}
    for k, e in full_bank.items():
        if e.get("jlpt") == level and k not in have:
            deck.append({**e, "src": "bank"})

    # 依詞性分類學習（名詞／動詞／形容詞）
    def _pos_group(p: str) -> str:
        if "動詞" in p:
            return "動詞"
        if "形容" in p:
            return "形容詞"
        if "名詞" in p or "代名" in p:
            return "名詞"
        return "其他"

    if deck:
        avail = [g for g in ["名詞", "動詞", "形容詞", "其他"]
                 if any(_pos_group(d.get("pos", "")) == g for d in deck)]
        pick = st.radio("詞性分類", ["全部"] + avail, horizontal=True, key=f"fc_pos_{level}")
        if pick != "全部":
            deck = [d for d in deck if _pos_group(d.get("pos", "")) == pick]

    if not deck:
        st.info("此分類尚無單字卡。可切換詞性，或到本頁「🤖 AI 單字庫」分頁生成更多字。")
        return

    ikey, fkey = f"fc_idx_{level}", f"fc_flip_{level}"
    st.session_state.setdefault(ikey, 0)
    st.session_state.setdefault(fkey, False)
    st.session_state[ikey] %= len(deck)
    idx = st.session_state[ikey]
    card = deck[idx]
    learned = st.session_state.progress[level]
    st.caption(f"📍 {idx + 1} / {len(deck)}　·　已學會 {len(learned)} 字")

    with st.container(border=True):
        if not st.session_state[fkey]:
            st.markdown(f"# {card['word']}　{'✅' if card['word'] in learned else ''}")
            line = []
            if card.get("kana"):
                line.append(f"假名 **{card['kana']}**")
            if card.get("romaji"):
                line.append(f"羅馬 `{card['romaji']}`")
            if line:
                st.markdown("　|　".join(line))
            if card.get("mnemonic"):
                st.markdown(f"📣 諧音 **{card['mnemonic']}**")
            if card.get("image"):
                st.caption(f"🖼️ {card['image']}")
            play_button(card["word"], key=f"fc_play_{level}_{idx}")
        else:
            st.markdown(f"# {card.get('meaning_zh', '')}")
            if card.get("example_jp"):
                st.markdown(f"💬 {card['example_jp']}")
                if card.get("example_zh"):
                    st.markdown(f"🇹🇼 {card['example_zh']}")
                play_button(card["example_jp"], key=f"fc_explay_{level}_{idx}")
            if card.get("usage_zh"):
                st.markdown(f"💡 {card['usage_zh']}")
            if card.get("pos"):
                st.caption(f"詞性：{card['pos']}")

    b1, b2, b3, b4, b5 = st.columns(5)
    if b1.button("← 上一個", use_container_width=True, key=f"fc_prev_{level}"):
        st.session_state[ikey] = (idx - 1) % len(deck)
        st.session_state[fkey] = False
        st.rerun()
    if b2.button("🔄 翻面", use_container_width=True, key=f"fc_flipbtn_{level}"):
        st.session_state[fkey] = not st.session_state[fkey]
        st.rerun()
    done = card["word"] in learned
    if b3.button("↩︎ 取消學會" if done else "✅ 標記學會",
                 use_container_width=True, key=f"fc_learn_{level}"):
        if done:
            learned.discard(card["word"])
        else:
            learned.add(card["word"])
        st.rerun()
    if b4.button("🎲 隨機", use_container_width=True, key=f"fc_rand_{level}"):
        import random
        st.session_state[ikey] = random.randrange(len(deck))
        st.session_state[fkey] = False
        st.rerun()
    if b5.button("下一個 →", use_container_width=True, key=f"fc_next_{level}"):
        st.session_state[ikey] = (idx + 1) % len(deck)
        st.session_state[fkey] = False
        st.rerun()


# ===========================================================================
# 🤖 AI 情境生成（Gemini → 心智圖 + 句卡）
# ===========================================================================
def page_ai_generate(level: str) -> None:
    st.header(f"🤖 {data.LEVELS[level]['label']} AI 情境生成")
    with st.expander("💡 這是什麼？怎麼用？", expanded=False):
        st.markdown(
            "**情境生成**＝把你想練的「真實場景」一鍵變成可學的日文內容。\n\n"
            "輸入生活情境（例如：在餐廳點餐、跟同事打招呼、向店員退貨），按「生成 ✨」，"
            "Gemini 會依目前 JLPT 級別產出**對話心智圖**與 **3–5 張句卡**"
            "（日文 + 假名 + 羅馬拼音 + 中文 + 文法 + 台味諧音）。喜歡的可「加入複習」做 SRS。"
        )

    if not ai.get_api_key():
        st.warning("尚未設定 Gemini API 金鑰，無法生成。")
        st.markdown(
            "- **Streamlit Cloud**：Settings → Secrets 加入 `GEMINI_API_KEY = \"你的_key\"`\n"
            "- **本機**：`export GEMINI_API_KEY=你的_key`\n"
            "- 取得：https://aistudio.google.com/apikey"
        )
        return

    rand = st.button("🎲 隨機生成情境", type="primary", use_container_width=True,
                     key=f"gen_rand_{level}")
    with st.expander("✍️ 想指定情境自己生成？", expanded=False):
        with st.form(f"gen_form_{level}", clear_on_submit=False):
            scenario = st.text_input("目標情境",
                                     placeholder="例如：在餐廳點餐並反映送錯餐點")
            model_label = st.selectbox("生成模型", ai.GEN_MODEL_TIERS, key=f"gen_tier_{level}")
            submitted = st.form_submit_button("生成 ✨")

    gen_scn, tier = None, next(iter(ai.GEN_MODEL_TIERS))
    if rand:
        gen_scn = random.choice(_JP_DIALOGUE_TOPICS)
    elif submitted and scenario.strip():
        gen_scn, tier = scenario.strip(), model_label
    elif submitted:
        st.warning("請先輸入情境。")

    if gen_scn:
        with st.spinner("生成中…"):
            try:
                raw = ai.generate_material(gen_scn, level, tier)
                mermaid, cards = ai.parse_blocks(raw)
                st.session_state.gen_result = {
                    "scenario": gen_scn, "level": level,
                    "mermaid": mermaid, "flashcards": cards or [], "raw": raw,
                }
            except Exception as e:  # noqa: BLE001
                st.session_state.gen_result = None
                st.error(_friendly_gen_error(str(e)))

    result = st.session_state.get("gen_result")
    if result:
        st.divider()
        st.markdown(f"#### 📍 情境：{result['scenario']}（{result.get('level', '')}）")
        if result["mermaid"]:
            render_mermaid(result["mermaid"])
            with st.expander("🔍 檢視 Mermaid 原始碼 / Gemini 完整回應"):
                st.code(result["mermaid"], language="text")
                st.code(result.get("raw", ""), language="text")
        else:
            st.info("未能解析出心智圖。")
            with st.expander("檢視 Gemini 原始回應"):
                st.code(result.get("raw", ""), language="text")

        if result["flashcards"]:
            st.markdown("#### 🃏 句卡")
            render_sentence_cards(result["flashcards"], key_prefix=f"gen_{level}")
        else:
            st.info("未能解析出句卡。")

        c1, c2, c3 = st.columns(3)
        if c1.button("💾 儲存這課", type="primary", use_container_width=True,
                     key=f"gen_save_{level}"):
            lessons = st.session_state.app_data.setdefault("lessons", [])
            new_id = max((l["id"] for l in lessons), default=0) + 1
            lessons.append({"id": new_id, "scenario": result["scenario"],
                            "level": result.get("level", ""), "mermaid": result["mermaid"],
                            "flashcards": result["flashcards"], "created": today_str()})
            save_data()
            st.session_state.gen_result = None
            st.success("已儲存到下方課程清單。")
            st.rerun()
        if c2.button("➕ 加入複習", use_container_width=True,
                     disabled=not result["flashcards"], key=f"gen_rev_{level}"):
            n = add_cards_to_review(result["flashcards"])
            st.success(f"已加入 {n} 張到複習清單。" if n else "這些句卡已在複習清單中。")
        if c3.button("🗑️ 清除結果", use_container_width=True, key=f"gen_clear_{level}"):
            st.session_state.gen_result = None
            st.rerun()

    lessons = st.session_state.app_data.get("lessons", [])
    if lessons:
        st.divider()
        st.markdown("### 📂 已儲存的情境課程")
        for lesson in reversed(lessons):
            with st.expander(f"📍 {lesson['scenario']}"
                             f"（{lesson.get('level', '')}　{lesson.get('created', '')}）"):
                if lesson.get("mermaid"):
                    render_mermaid(lesson["mermaid"])
                if lesson.get("flashcards"):
                    render_sentence_cards(lesson["flashcards"],
                                          key_prefix=f"lesson_{lesson['id']}")
                lc1, lc2 = st.columns(2)
                if lc1.button("➕ 加入複習", key=f"lesson_rev_{lesson['id']}",
                              use_container_width=True,
                              disabled=not lesson.get("flashcards")):
                    n = add_cards_to_review(lesson["flashcards"])
                    st.success(f"已加入 {n} 張。" if n else "已在複習清單中。")
                if lc2.button("🗑️ 刪除這課", key=f"lesson_del_{lesson['id']}",
                              use_container_width=True):
                    st.session_state.app_data["lessons"] = [
                        l for l in lessons if l["id"] != lesson["id"]]
                    save_data()
                    st.rerun()


# ===========================================================================
# 📖 單字庫（AI 雲端生成 + JSON 下載 + GitHub 推回）
# ===========================================================================
def page_vocab_bank(level: str) -> None:
    st.header("📖 單字庫")
    with st.expander("💡 這是什麼？怎麼用？", expanded=False):
        st.markdown(
            "**單字庫**＝可成長的日文單字資料庫，每筆含假名、羅馬拼音、中文、台味諧音、"
            "圖像聯想、口語例句、用法、JLPT 級別。\n\n"
            "1. 展開「🤖 用 AI 在雲端即時生成」按「🚀 開始生成」（從 "
            "`scripts/vocab_wordlist.txt` 取尚未做過的字）\n"
            "2. 想永久保存：設定 `GITHUB_TOKEN` 後自動推回，或手動「⬇️ 下載」覆蓋 repo 的 "
            "`vocab_bank.json`\n"
            "3. 生成的字會自動出現在「🃏 單字卡」對應 JLPT 級別的 deck"
        )
    file_bank = ai.load_vocab_bank()
    live_bank = st.session_state.setdefault("live_bank", {})
    synced = st.session_state.get("synced_bank", {})
    bank = {**file_bank, **synced, **live_bank}
    api_key = ai.get_api_key()

    with st.expander("🤖 用 AI 在雲端即時生成（無需本機）", expanded=not bank):
        if not api_key:
            st.warning("尚未設定 Gemini API 金鑰。請至 Cloud Secrets 加入 `GEMINI_API_KEY`。")
        else:
            n_total = len(ai.get_all_api_keys())
            n_avail = sum(1 for k in ai.get_all_api_keys()
                          if k not in st.session_state.get("_exhausted_keys", set()))
            st.caption(f"供應商：**Google Gemini**　·　偵測到 **{n_total} 把 key**"
                       f"（{n_avail} 把可用）。撞 429 自動換下一把。")
        c1, c2, c3 = st.columns([2, 2, 2])
        n = c1.number_input("一次生成幾個字", min_value=5, max_value=50, value=20, step=5)
        tier = c2.selectbox("模型", ai.GEN_MODEL_TIERS, index=0, key="bank_tier")
        gh = ai.get_github_token()
        if gh:
            st.caption("🔄 **自動推回**已啟用：生成完會 commit 回 repo，Cloud 重新部署後永久保存。")
        else:
            st.warning("⚠️ 未設 `GITHUB_TOKEN`，生成的字只留在 session，**重整就消失**。"
                       "可手動按下方「⬇️ 下載」保存。")
        if c3.button("🚀 開始生成", disabled=not api_key, use_container_width=True,
                     type="primary"):
            _run_inapp_generation(int(n), tier, auto_push=bool(gh))
            st.rerun()

        try:
            from scripts.generate_vocab import load_wordlist
            wl = len(load_wordlist())
        except Exception:  # noqa: BLE001
            wl = 0
        st.caption(f"詞表 {wl} 字　·　已完成 **{len(bank)}** 字"
                   f"　·　📁 部署檔 {len(file_bank)} / ☁️ 已推 GitHub {len(synced)} / 🌱 待推 {len(live_bank)}")
        last = st.session_state.get("_last_push")
        if last:
            (st.success if last["ok"] else st.error)(
                f"📤 最後一次推回：{last['ts']} "
                + ("成功" if last["ok"] else "**失敗** — 請手動下載 JSON 保存！"))
        if live_bank:
            st.error(f"🚨 session 有 {len(live_bank)} 個新生成的字尚未進 repo！"
                     "重整就會消失，請按下方「⬇️ 下載」先存到本機。")

    if bank:
        cdl, cpush = st.columns([3, 2])
        merged_json = json.dumps(bank, ensure_ascii=False, indent=2) + "\n"
        cdl.download_button("⬇️ 下載合併後 vocab_bank.json", data=merged_json,
                            file_name="vocab_bank.json", mime="application/json",
                            use_container_width=True)
        if cpush.button("🚀 立即推回 GitHub repo",
                        disabled=not ai.get_github_token() or not live_bank,
                        use_container_width=True):
            ok, info = ai.push_bank_to_github(bank)
            _record_push(ok, info, merged=bank)
            st.rerun()

    if not bank:
        st.info("單字庫是空的。展開上方面板用 AI 即時生成，"
                "或本機跑 `python scripts/generate_vocab.py` 後 push 回 repo。")
        return

    err = st.session_state.get("_push_error")
    if err:
        with st.expander("🩺 上次推回失敗的詳細原因", expanded=True):
            st.markdown(f"- **階段**：`{err.get('stage')}`　**HTTP**：`{err.get('code')}`\n"
                        f"- **Repo**：`{err.get('repo')}@{err.get('branch')}`")
            st.code(err.get("body", ""), language="json")
            st.caption("403 → token 沒 Contents:Write（改用 Classic PAT 勾 repo 最快）；"
                       "404 → repo 名稱/branch 錯；422 → sha 衝突，重按推回。")

    # 搜尋 + 分頁
    words = sorted(bank.keys())
    query = st.text_input("搜尋（日文／中文／諧音）",
                          placeholder="輸入單字、諧音或中文意思片段").strip()
    if query:
        def _match(w):
            e = bank[w]
            return (query in w or query in (e.get("meaning_zh") or "")
                    or query in (e.get("kana") or "")
                    or query in (e.get("mnemonic") or ""))
        words = [w for w in words if _match(w)]

    per_page = 10
    total_pages = max(1, (len(words) + per_page - 1) // per_page)
    page = st.number_input("頁", min_value=1, max_value=total_pages, value=1, step=1) - 1
    st.caption(f"庫存 {len(bank)} 字　|　符合 {len(words)} 字　|　頁 {page + 1}/{total_pages}")

    for w in words[page * per_page:(page + 1) * per_page]:
        e = bank[w]
        with st.container(border=True):
            c1, c2 = st.columns([2, 5])
            c1.markdown(f"### {w}")
            if e.get("jlpt"):
                c1.caption(f"🏷️ {e['jlpt']}")
            if e.get("kana"):
                c1.caption(f"假名 {e['kana']}")
            if e.get("romaji"):
                c1.caption(f"羅馬 `{e['romaji']}`")
            if e.get("meaning_zh"):
                c2.markdown(f"**{e['meaning_zh']}**")
            if e.get("mnemonic"):
                c2.markdown(f"📣 諧音 **{e['mnemonic']}**")
            if e.get("image"):
                c2.markdown(f"🖼️ {e['image']}")
            if e.get("example_jp"):
                c2.markdown(f"💬 *{e['example_jp']}*")
            if e.get("example_zh"):
                c2.markdown(f"🇹🇼 {e['example_zh']}")
            if e.get("usage_zh"):
                c2.caption(f"💡 {e['usage_zh']}")


def _record_push(ok: bool, info: dict, merged: dict | None = None) -> None:
    """記錄推回結果到 session，供 UI 顯示。

    推回成功時，除了清空 live_bank，必須把合併結果同步寫回「本機」vocab_bank.json，
    否則本機檔仍是部署當下的舊版，畫面會誤顯示舊字數（使用者回報的「資料庫不會更新」）。
    寫本機後清快取，load_vocab_bank 立即讀到新字數，遠端與本機一致。
    """
    import datetime as _dt
    st.session_state["_last_push"] = {"ok": ok, "ts": _dt.datetime.now().strftime("%H:%M:%S")}
    if ok:
        st.session_state.pop("_push_error", None)
        # 嘗試寫本機（Cloud /mount/src 多唯讀，靜默失敗，故不依賴它）
        if merged is not None:
            try:
                with open(ai.VOCAB_BANK_FILE, "w", encoding="utf-8") as f:
                    json.dump(merged, f, ensure_ascii=False, indent=2)
                for fn in (ai.load_vocab_bank, ai._load_vocab_bank_cached):
                    if hasattr(fn, "clear"):
                        fn.clear()
            except OSError:
                pass
        # 關鍵：把已推回的字移進 session「已同步層」(不清空)，畫面才會立即顯示新總數
        live = st.session_state.get("live_bank", {})
        st.session_state.setdefault("synced_bank", {}).update(live)
        st.session_state["live_bank"] = {}
    else:
        st.session_state["_push_error"] = info


def _run_inapp_generation(n: int, tier: str, auto_push: bool = False) -> None:
    """雲端內用 Gemini 生成 N 字，寫進 st.session_state.live_bank（三重去重）。"""
    from scripts.generate_vocab import load_wordlist
    file_bank = ai.load_vocab_bank()
    live = st.session_state.setdefault("live_bank", {})
    synced = st.session_state.get("synced_bank", {})
    have = set(file_bank) | set(live) | set(synced)
    todo = [w for w in load_wordlist() if w["word"] not in have][:n]
    if not todo:
        st.success("詞表已全數完成，沒有待補單字。可編輯 `scripts/vocab_wordlist.txt` 增字。")
        return
    todo_set = {w["word"] for w in todo}
    try:
        with st.spinner(f"用 Gemini（{tier}）生成 {len(todo)} 字…"):
            entries = ai.generate_vocab_batch(todo, tier)
    except Exception as e:  # noqa: BLE001
        st.error(_friendly_gen_error(str(e)))
        return

    added, new_words = 0, []
    for e in entries:
        ww = (e.get("word") or "").strip()
        if ww in todo_set and ww not in have and e.get("meaning_zh") and e.get("kana"):
            live[ww] = e
            have.add(ww)
            new_words.append(ww)
            added += 1
    st.success(f"✅ 已生成 {added} 字：{'、'.join(new_words[:10])}"
               f"{' …' if len(new_words) > 10 else ''}")
    if auto_push and added:
        merged = {**file_bank, **live}
        ok, info = ai.push_bank_to_github(merged)
        _record_push(ok, info, merged=merged)
        if not ok:
            st.error(f"⚠️ 這批 {added} 字推回失敗，只留在 session，重整就消失！請手動下載 JSON。")


def _friendly_gen_error(msg: str) -> str:
    if any(h in msg for h in ai._QUOTA_HINTS):
        return ("⏰ Gemini 免費額度用完了（Google 每日上限）。解法：上方下拉改選 "
                "「Flash-Lite」或「2.0 Flash」（額度多 10 倍）；或等明天 UTC 0:00 重置；"
                "或到 https://aistudio.google.com/apikey 開新 project 再生一把 key。")
    if any(h in msg for h in ai._TRANSIENT_HINTS):
        return "⏳ Google 伺服器忙碌（503）。請等 30 秒～2 分鐘再試，或改用負載較輕的模型。"
    if "API key not valid" in msg or "API_KEY_INVALID" in msg:
        return ("❌ Google 拒絕了你的 API key。請到 https://aistudio.google.com/apikey "
                "重新「Create API key in new project」貼回 Secrets。")
    return f"生成失敗：{msg}"


# ===========================================================================
# 🔁 複習（SRS）
# ===========================================================================
def page_review() -> None:
    st.header("🔁 複習")
    deck = st.session_state.app_data.setdefault("review_cards", [])
    if not deck:
        st.info("複習清單是空的。到「🤖 AI 情境生成」把句卡加入複習。")
        return

    today = today_str()
    due = [c for c in deck if c.get("due", today) <= today]
    st.caption(f"清單共 {len(deck)} 張，今天到期 {len(due)} 張。")

    if not due:
        nxt = min((c.get("due", today) for c in deck), default=today)
        st.success(f"今天沒有要複習的卡 🎉 下次到期：{nxt}")
        with st.expander("清空複習清單"):
            if st.button("確認清空", type="primary"):
                st.session_state.app_data["review_cards"] = []
                save_data()
                st.rerun()
        return

    card = due[0]
    st.progress((len(deck) - len(due)) / len(deck), text=f"剩 {len(due)} 張待複習")
    st.markdown(f"## {card.get('sentence', '')}")

    if st.session_state.get("review_reveal_id") != card["id"]:
        if st.button("🔄 翻面看答案", type="primary", use_container_width=True):
            st.session_state.review_reveal_id = card["id"]
            st.rerun()
        return

    render_sentence_cards([card], key_prefix="review")
    g1, g2, g3 = st.columns(3)
    graded = None
    if g1.button("😵 忘記", use_container_width=True):
        graded = "again"
    if g2.button("🙂 普通", use_container_width=True):
        graded = "good"
    if g3.button("😎 簡單", use_container_width=True):
        graded = "easy"
    if graded:
        schedule_card(card, graded)
        save_data()
        st.session_state.pop("review_reveal_id", None)
        st.rerun()


# ===========================================================================
# 📊 學習儀表板（科學監督：記憶強度、複習負擔預測）
# ===========================================================================
def page_dashboard(level: str) -> None:
    st.header("📊 學習儀表板")
    st.caption("用間隔重複（SRS）追蹤你的記憶狀態：今日待複習、記憶強度分布、未來複習負擔。")

    deck = st.session_state.app_data.get("review_cards", [])
    if not deck:
        st.info("複習牌組是空的。到「💬 情境會話」各分頁（AI 生活對話／情境心智圖／AI 互動閱讀）"
                "把句卡「加入複習」，系統就會用間隔重複幫你科學排程並在這裡呈現記憶分析。")
        return

    dist = mastery_distribution()
    total = len(deck)
    mature = dist["young"] + dist["mature"]
    today = today_str()
    studied = sum(1 for c in deck if c.get("reps", 0) > 0)
    reviews_total = sum(c.get("reps", 0) for c in deck)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("🃏 複習卡總數", total)
    c2.metric("📅 今日待複習", due_count())
    c3.metric("🌳 已熟（漸熟+掌握）", mature)
    c4.metric("💪 熟練比例", f"{int(mature / total * 100) if total else 0}%")

    st.divider()
    st.subheader("🎯 記憶強度分布")
    labels = {"new": "🆕 新卡", "learning": "📖 學習中（<7天）",
              "young": "🌱 漸熟（7–20天）", "mature": "🌳 已掌握（≥21天）"}
    mc = st.columns(4)
    for col, k in zip(mc, ["new", "learning", "young", "mature"]):
        col.metric(labels[k], dist.get(k, 0))
    st.caption(f"已開始複習 {studied}／{total} 張　·　累計複習次數 {reviews_total}")

    st.subheader("📈 未來 7 天複習負擔預測")
    st.caption("提早知道哪天卡片會堆積，方便分配每天的學習時間。")
    st.bar_chart({"到期張數": review_forecast(7)}, height=240)


# ===========================================================================
# 🗣️ AI 生活對話（Gemini → 雙語對話 + 文法重點）
# ===========================================================================
_JP_DIALOGUE_TOPICS = [
    "コンビニで会計", "レストランで注文", "道を尋ねる", "美容院で予約",
    "病院で症状を説明", "友達を食事に誘う", "ホテルのチェックイン", "宅配便の受け取り",
    "駅で切符を買う", "同僚と週末の話", "大家さんに修理をお願い", "服を試着する",
    "電話で問い合わせ", "カフェで注文", "面接の自己紹介", "近所の人と挨拶",
    "ジムの入会相談", "落とし物を届ける", "天気の話で雑談", "誕生日を祝う",
]


def page_ai_dialogue(level: str) -> None:
    st.header(f"🗣️ {data.LEVELS[level]['label']} AI 生活對話")
    with st.expander("💡 這是什麼？怎麼用？", expanded=False):
        st.markdown(
            "**生活對話**＝把你想練的場景一鍵生成一段日本人的自然對話。\n\n"
            "輸入情境（例如：在便利商店結帳、跟房東報修、跟朋友約吃飯），按「生成 ✨」，"
            "Gemini 會依目前 JLPT 級別產出 **6–10 句雙語對話**（每句可發音）＋ **文法重點**。"
            "喜歡的對話可整段「加入複習」做 SRS。"
        )

    submitted, scenario, model_label = False, "", next(iter(ai.GEN_MODEL_TIERS))
    if not ai.get_api_key():
        st.warning("尚未設定 Gemini 金鑰，無法「生成」新對話（下方已累積的對話仍可閱讀）。"
                   "請至側欄或 Cloud Secrets 設定 `GEMINI_API_KEY`。")
    else:
        # 🎲 隨機生成：自動挑情境，一鍵冒出新對話並累積
        if st.button("🎲 隨機生成情境對話", type="primary", use_container_width=True,
                     key=f"dlg_rand_{level}"):
            used = {d.get("title") for d in
                    _level_items(ai.load_dialogue_bank(), "_sess_dialogue", level, "id")}
            pool = [t for t in _JP_DIALOGUE_TOPICS if t not in used] or _JP_DIALOGUE_TOPICS
            try:
                with st.spinner("生成中…"):
                    dlg = ai.gen_dialogue(random.choice(pool), level, model_label)
                st.session_state[f"dlg_result_{level}"] = dlg
                try:
                    _, ok = _persist_dialogue_jp(dlg, level)
                except Exception:  # noqa: BLE001
                    ok = False
                st.session_state["_dlg_saved"] = ok
                st.rerun()
            except Exception as e:  # noqa: BLE001
                st.error(_friendly_gen_error(str(e)))
        with st.expander("✍️ 想指定情境自己生成？", expanded=False), \
                st.form(f"dlg_form_{level}", clear_on_submit=False):
            scenario = st.text_input("對話情境",
                                     placeholder="例如：在便利商店結帳並詢問有沒有熱食")
            model_label = st.selectbox("生成模型", ai.GEN_MODEL_TIERS, key=f"dlg_tier_{level}")
            submitted = st.form_submit_button("生成 ✨", type="primary")

    if st.session_state.pop("_dlg_saved", None):
        st.success("已生成並存進對話庫（下方「已累積的對話」持續長大）。")

    if submitted:
        if not scenario.strip():
            st.warning("請先輸入情境。")
        else:
            try:
                with st.spinner("生成中…"):
                    dlg = ai.gen_dialogue(scenario.strip(), level, model_label)
                st.session_state[f"dlg_result_{level}"] = dlg  # 先存確保看得到
                try:
                    _, ok = _persist_dialogue_jp(dlg, level)
                except Exception:  # noqa: BLE001
                    ok = False
                st.session_state["_dlg_saved"] = ok
                st.rerun()
            except Exception as e:  # noqa: BLE001
                st.session_state.pop(f"dlg_result_{level}", None)
                st.error(_friendly_gen_error(str(e)))

    dlg = st.session_state.get(f"dlg_result_{level}")
    if dlg and dlg.get("lines"):
        st.divider()
        st.markdown(f"#### 📍 {dlg.get('title', '')}　{dlg.get('title_zh', '')}")
        if dlg.get("scene"):
            st.caption(f"場景：{dlg['scene']}")
        for i, ln in enumerate(dlg["lines"]):
            with st.container(border=True):
                st.markdown(f"**{ln.get('speaker', '')}：** {ln.get('jp', '')}")
                meta = []
                if ln.get("kana"):
                    meta.append(f"假名 `{ln['kana']}`")
                if meta:
                    st.caption("　".join(meta))
                if ln.get("zh"):
                    st.markdown(f"🇹🇼 {ln['zh']}")
                if ln.get("jp"):
                    play_button(ln["jp"], key=f"dlg_play_{level}_{i}")
        if dlg.get("grammar"):
            st.markdown("##### 📚 文法重點")
            for g in dlg["grammar"]:
                with st.container(border=True):
                    st.markdown(f"**🎯 {g.get('point', '')}**")
                    if g.get("explain"):
                        st.caption(g["explain"])
                    if g.get("example"):
                        st.markdown(f"　- `{g['example']}`")

        c1, c2 = st.columns(2)
        if c1.button(f"➕ 加入 {len(dlg['lines'])} 句到複習",
                     use_container_width=True, key=f"dlg_rev_{level}"):
            cards = [
                {"sentence": ln["jp"], "kana": ln.get("kana", ""),
                 "chinese": ln.get("zh", ""), "chunk": ln["jp"][:20],
                 "context": f"對話：{dlg.get('title', '')}"}
                for ln in dlg["lines"] if ln.get("jp")
            ]
            n = add_cards_to_review(cards)
            st.success(f"已加入 {n} 句到複習清單。" if n else "這些句子已在複習清單中。")
        if c2.button("🗑️ 清除結果", use_container_width=True, key=f"dlg_clear_{level}"):
            st.session_state.pop(f"dlg_result_{level}", None)
            st.rerun()

    # 📚 已累積的對話（永久庫，越長越多）
    bank = _level_items(ai.load_dialogue_bank(), "_sess_dialogue", level, "id")
    if bank:
        st.divider()
        st.markdown(f"### 📚 已累積的對話（{level} 共 {len(bank)} 段）")
        st.caption("歷次 AI 生成、已存進資料庫的對話，隨時可重讀、加入複習。")
        for bi, d in enumerate(reversed(bank)):
            with st.expander(f"📍 {d.get('title','')}　{d.get('title_zh','')}"):
                if d.get("scene"):
                    st.caption(f"場景：{d['scene']}")
                for i, ln in enumerate(d.get("lines", [])):
                    st.markdown(f"**{ln.get('speaker','')}：** {ln.get('jp','')}")
                    if ln.get("kana"):
                        st.caption(f"假名 `{ln['kana']}`　🇹🇼 {ln.get('zh','')}")
                    if ln.get("jp"):
                        play_button(ln["jp"], key=f"dlgbank_play_{level}_{bi}_{i}")
                if st.button(f"➕ 加入 {len(d.get('lines',[]))} 句到複習",
                             key=f"dlgbank_rev_{level}_{bi}", use_container_width=True):
                    cards = [{"sentence": ln["jp"], "kana": ln.get("kana", ""),
                              "chinese": ln.get("zh", ""), "chunk": ln["jp"][:20],
                              "context": f"對話：{d.get('title','')}"}
                             for ln in d.get("lines", []) if ln.get("jp")]
                    n = add_cards_to_review(cards)
                    st.success(f"已加入 {n} 句。" if n else "已在複習清單中。")


# ===========================================================================
# 📚 AI 互動閱讀（書籍／文章 → 可點字看翻譯 + 發音 + 文法）
# ===========================================================================
# 隨機生成用的多元日文閱讀主題池（每按一次都不同，源源不絕）
_JP_READING_TOPICS = [
    "桃太郎の物語", "私の一日", "環境保護", "日本の四季", "コンビニでの買い物",
    "電車での通勤", "祖母の思い出", "初めての一人暮らし", "好きな食べ物",
    "週末の過ごし方", "夢に向かって", "引っ越しの一日", "雨の日の過ごし方",
    "友達との約束", "新しい趣味", "健康な生活", "旅行の計画", "図書館での出来事",
    "猫との暮らし", "失敗から学んだこと", "お祭りの思い出", "料理に挑戦",
    "日本語の勉強法", "町の小さな店", "季節の変わり目", "夜空を見上げて",
    "古い手紙", "見知らぬ人の親切", "技術と私たちの生活", "ふるさとの風景",
]


def _persist_reading_jp(reading: dict, level: str) -> tuple:
    """把生成的閱讀加入永久庫：寫本機 + 推回 GitHub，讓資料庫持續長大。回傳 (ok, info)。"""
    reading.setdefault("level", level)
    bank = list(ai.load_readings_bank())
    ids = {r.get("id") for r in bank}
    rid = reading.get("id") or reading.get("title", "")
    reading["id"] = rid if rid and rid not in ids else f"{rid or 'rd'}-{len(bank)}"
    bank.append(reading)
    st.session_state.setdefault("_sess_readings", []).append(reading)  # 立即可見
    payload = json.dumps(bank, ensure_ascii=False, indent=2) + "\n"
    try:
        with open(ai.READINGS_BANK_FILE, "w", encoding="utf-8") as f:
            f.write(payload)
    except OSError:
        pass
    for fn in (ai.load_readings_bank, ai._load_readings_bank_cached):
        if hasattr(fn, "clear"):
            fn.clear()
    return ai.github_put_file(
        "readings_bank.json", payload,
        f"readings_bank: AI 生成新增「{reading.get('title','')}」（共 {len(bank)} 篇）")


def _persist_dialogue_jp(dlg: dict, level: str) -> tuple:
    """把生成的對話加入永久庫：寫本機 + 推回 GitHub。回傳 (bank長度, ok)。"""
    dlg.setdefault("level", level)
    bank = list(ai.load_dialogue_bank())
    ids = {d.get("id") for d in bank}
    rid = dlg.get("id") or dlg.get("title", "")
    dlg["id"] = rid if rid and rid not in ids else f"{rid or 'dlg'}-{len(bank)}"
    bank.append(dlg)
    st.session_state.setdefault("_sess_dialogue", []).append(dlg)  # 立即可見
    payload = json.dumps(bank, ensure_ascii=False, indent=2) + "\n"
    try:
        with open(ai.DIALOGUE_BANK_FILE, "w", encoding="utf-8") as f:
            f.write(payload)
    except OSError:
        pass
    for fn in (ai.load_dialogue_bank, ai._load_dialogue_bank_cached):
        if hasattr(fn, "clear"):
            fn.clear()
    ok, _info = ai.github_put_file(
        "dialogue_bank.json", payload,
        f"dialogue_bank: AI 生成新增「{dlg.get('title','')}」（共 {len(bank)} 段）")
    return len(bank), ok


def _do_generate_reading(topic: str, level: str, model_label: str) -> None:
    """生成一篇閱讀 → 存進永久庫 → 設為當前顯示結果。"""
    with st.spinner(f"生成「{topic}」中…"):
        rd = ai.gen_reading(topic, level, model_label)
    # 先設為顯示結果，確保一定看得到；存檔/推回出錯也不影響「已生成」
    st.session_state[f"rd_result_{level}"] = rd
    try:
        ok, _info = _persist_reading_jp(rd, level)
    except Exception:  # noqa: BLE001
        ok = False
    st.session_state["_rd_saved"] = ok


def page_ai_reading(level: str) -> None:
    st.header(f"📚 {data.LEVELS[level]['label']} AI 互動閱讀")
    with st.expander("💡 這是什麼？怎麼用？", expanded=False):
        st.markdown(
            "**互動閱讀**＝AI 依 JLPT 級別生成日文閱讀，附整句假名、中文翻譯、重點單字與文法。\n\n"
            "按「🎲 隨機生成」一鍵冒出全新文章；生成的閱讀會**永久存進資料庫並持續累積**"
            "（需設定 `GITHUB_TOKEN`），下方「已累積的閱讀」隨時可重讀。"
        )

    if st.session_state.pop("_rd_saved", None):
        st.success("已生成並永久存入資料庫！下方「已累積的閱讀」會越來越多。")

    # 生成 UI 需要金鑰；沒金鑰仍可閱讀下方已累積的文章
    if not ai.get_api_key():
        st.warning("尚未設定 Gemini API 金鑰，無法「生成」新閱讀（下方已累積的文章仍可閱讀）。"
                   "請至側欄或 Cloud Secrets 設定 `GEMINI_API_KEY`"
                   "（取得：https://aistudio.google.com/apikey）。")
    else:
        model_label = next(iter(ai.GEN_MODEL_TIERS))
        rc1, rc2 = st.columns([3, 2])
        if rc1.button("🎲 隨機生成一篇新閱讀", type="primary", use_container_width=True,
                      key=f"rd_rand_{level}",
                      help="自動挑一個主題，依目前級別生成全新閱讀。每按一次都不一樣。"):
            used = {r.get("title") for r in ai.load_readings_bank()}
            pool = [t for t in _JP_READING_TOPICS if t not in used] or _JP_READING_TOPICS
            try:
                _do_generate_reading(random.choice(pool), level, model_label)
                st.rerun()
            except Exception as e:  # noqa: BLE001
                st.error(_friendly_gen_error(str(e)))
        rc2.caption(f"📚 資料庫已累積 **{len(ai.load_readings_bank())}** 篇")

        with st.expander("✍️ 想指定主題自己生成？", expanded=False):
            with st.form(f"rd_form_{level}", clear_on_submit=False):
                topic = st.text_input("主題／書籍",
                                      placeholder="例如：桃太郎的故事 / 我的一天 / 環境保護")
                tier = st.selectbox("生成模型", ai.GEN_MODEL_TIERS, key=f"rd_tier_{level}")
                submitted = st.form_submit_button("生成 ✨")
            if submitted:
                if not topic.strip():
                    st.warning("請先輸入主題。")
                else:
                    try:
                        _do_generate_reading(topic.strip(), level, tier)
                        st.rerun()
                    except Exception as e:  # noqa: BLE001
                        st.session_state.pop(f"rd_result_{level}", None)
                        st.error(_friendly_gen_error(str(e)))

    rd = st.session_state.get(f"rd_result_{level}")
    if rd and rd.get("sentences"):
        st.divider()
        st.markdown(f"#### 📖 {rd.get('title', '')}　{rd.get('title_zh', '')}")
        if rd.get("summary"):
            st.caption(rd["summary"])
        for i, s in enumerate(rd["sentences"]):
            with st.container(border=True):
                st.markdown(f"### {s.get('jp', '')}")
                if s.get("kana"):
                    st.caption(f"假名 `{s['kana']}`")
                if s.get("zh"):
                    st.markdown(f"🇹🇼 {s['zh']}")
                vocab = s.get("vocab") or {}
                if vocab:
                    st.markdown("📝 重點單字：" + "　".join(
                        f"**{w}**＝{m}" for w, m in vocab.items()))
                if s.get("grammar"):
                    st.markdown(f"📚 文法：{s['grammar']}")
                if s.get("jp"):
                    play_button(s["jp"], key=f"rd_play_{level}_{i}")

        c1, c2 = st.columns(2)
        if c1.button(f"➕ 加入 {len(rd['sentences'])} 句到複習",
                     use_container_width=True, key=f"rd_rev_{level}"):
            cards = [
                {"sentence": s["jp"], "kana": s.get("kana", ""),
                 "chinese": s.get("zh", ""), "chunk": s["jp"][:20],
                 "grammar": s.get("grammar", ""),
                 "context": f"閱讀：{rd.get('title', '')}"}
                for s in rd["sentences"] if s.get("jp")
            ]
            n = add_cards_to_review(cards)
            st.success(f"已加入 {n} 句到複習清單。" if n else "這些句子已在複習清單中。")
        if c2.button("🗑️ 清除結果", use_container_width=True, key=f"rd_clear_{level}"):
            st.session_state.pop(f"rd_result_{level}", None)
            st.rerun()

    # 📚 已累積的閱讀（永久庫，越長越多，重整不消失）
    bank = _level_items(ai.load_readings_bank(), "_sess_readings", None, "id")
    if bank:
        st.divider()
        st.markdown(f"### 📚 已累積的閱讀（共 {len(bank)} 篇）")
        st.caption("這些是歷次 AI 生成、已存進 GitHub 資料庫的閱讀，隨時可重讀。")
        for bi, r in enumerate(reversed(bank)):  # 新的排上面
            with st.expander(f"📖 {r.get('title','')}　{r.get('title_zh','')}"
                             f"　·　{r.get('level','')}"):
                if r.get("summary"):
                    st.caption(r["summary"])
                for i, s in enumerate(r.get("sentences", [])):
                    st.markdown(f"**{s.get('jp','')}**")
                    if s.get("kana"):
                        st.caption(f"假名 `{s['kana']}`")
                    if s.get("zh"):
                        st.caption(f"🇹🇼 {s['zh']}")
                    if s.get("jp"):
                        play_button(s["jp"], key=f"bank_play_{level}_{bi}_{i}")
                if st.button(f"➕ 加入 {len(r.get('sentences',[]))} 句到複習",
                             key=f"bank_rev_{level}_{bi}", use_container_width=True):
                    cards = [{"sentence": s["jp"], "kana": s.get("kana", ""),
                              "chinese": s.get("zh", ""), "chunk": s["jp"][:20],
                              "grammar": s.get("grammar", ""),
                              "context": f"閱讀：{r.get('title','')}"}
                             for s in r.get("sentences", []) if s.get("jp")]
                    n = add_cards_to_review(cards)
                    st.success(f"已加入 {n} 句。" if n else "已在複習清單中。")


def page_subtitles(level: str) -> None:
    """🎬 影視字幕學習：貼上日文台詞/字幕 → AI 逐句日翻中 + 教口語/慣用語/文法。"""
    st.header(f"🎬 {data.LEVELS[level]['label']} 影視字幕學習")
    with st.expander("💡 這是什麼？怎麼用？", expanded=False):
        st.markdown(
            "把真實影集／動畫／電影的日文台詞變成互動課程。\n\n"
            "1. 貼上一段日文台詞，或直接貼 `.srt` 字幕內容（時間軸會自動忽略）\n"
            "2. 按「🎬 生成字幕課程」→ AI **逐句日翻中** + 附假名、標出**口語／慣用語／文法**\n"
            "3. 可整段**加入複習（SRS）**，也會**存進閱讀庫永久累積**\n\n"
            "💡 影視台詞最道地，是教科書學不到的真實日文。"
        )

    if st.session_state.pop("_sub_saved", None):
        st.success("已生成並存進閱讀庫（可在「📚 AI 互動閱讀」重看，資料庫持續長大）。")

    if not ai.get_api_key():
        st.warning("需要 Gemini API 金鑰才能生成。請至側欄或 Cloud Secrets 設定 `GEMINI_API_KEY`。")
    else:
        raw = st.text_area("貼上日文台詞 / 字幕（.srt 也可）", height=200,
                           placeholder="例：\nお前はもう死んでいる。\nなに？\n\n（可直接貼字幕檔內容，序號與時間軸會自動忽略）",
                           key=f"sub_raw_{level}")
        c1, c2 = st.columns([2, 3])
        tier = c1.selectbox("生成模型", ai.GEN_MODEL_TIERS, key=f"sub_tier_{level}")
        if c2.button("🎬 生成字幕課程", type="primary", use_container_width=True,
                     disabled=not (raw and raw.strip())):
            try:
                with st.spinner("AI 逐句翻譯 + 教學中…"):
                    lesson = ai.gen_subtitle_lesson(raw, level, tier)
                st.session_state[f"sub_result_{level}"] = lesson  # 先存，確保看得到
                try:
                    ok, _info = _persist_reading_jp(lesson, level)
                except Exception:  # noqa: BLE001
                    ok = False
                st.session_state["_sub_saved"] = ok
                st.rerun()
            except Exception as e:  # noqa: BLE001
                st.error(_friendly_gen_error(str(e)))

    lesson = st.session_state.get(f"sub_result_{level}")
    if lesson and lesson.get("sentences"):
        st.divider()
        st.markdown(f"#### 🎬 {lesson.get('title', '')}　{lesson.get('title_zh', '')}")
        if lesson.get("summary"):
            st.caption(lesson["summary"])
        for i, s in enumerate(lesson["sentences"]):
            with st.container(border=True):
                st.markdown(f"### {s.get('jp', '')}")
                if s.get("kana"):
                    st.caption(f"假名 `{s['kana']}`")
                if s.get("zh"):
                    st.markdown(f"🇹🇼 {s['zh']}")
                vocab = s.get("vocab") or {}
                if vocab:
                    st.markdown("📝 重點：" + "　".join(f"**{w}**＝{m}" for w, m in vocab.items()))
                if s.get("grammar"):
                    st.markdown(f"📚 文法：{s['grammar']}")
                if s.get("jp"):
                    play_button(s["jp"], key=f"sub_play_{level}_{i}")
        if st.button(f"➕ 加入 {len(lesson['sentences'])} 句到複習",
                     use_container_width=True, key=f"sub_rev_{level}"):
            cards = [{"sentence": s["jp"], "kana": s.get("kana", ""),
                      "chinese": s.get("zh", ""), "chunk": s["jp"][:20],
                      "grammar": s.get("grammar", ""),
                      "context": f"字幕：{lesson.get('title', '')}"}
                     for s in lesson["sentences"] if s.get("jp")]
            n = add_cards_to_review(cards)
            st.success(f"已加入 {n} 句到複習清單。" if n else "這些句子已在複習清單中。")


def page_vocab_all(level: str) -> None:
    """單字庫：翻面學習單字卡 + AI 生成單字庫，以分頁呈現。"""
    st.header(f"📖 {data.LEVELS[level]['label']} 單字庫")
    st.caption("「單字卡」翻面學習（正面日文、翻面看中文/詞性/用法/例句，可依詞性分類）；"
               "「AI 單字庫」可無限生成、存進資料庫累積長大。")
    tab_card, tab_ai = st.tabs(["🃏 單字卡（翻面）", "🤖 AI 單字庫（可生成）"])
    with tab_card:
        page_flashcards(level)
    with tab_ai:
        page_vocab_bank(level)


def page_library(level: str) -> None:
    """📚 我的資料庫：所有 AI 生成並累積的內容（單字/文法/對話/閱讀）集中瀏覽。"""
    st.header("📚 我的資料庫")
    st.caption("所有 AI 生成、累積的內容都在這裡瀏覽——這些都會推到 GitHub 永久保存、持續長大。")

    vocab = {**ai.load_vocab_bank(),
             **st.session_state.get("synced_bank", {}),
             **st.session_state.get("live_bank", {})}
    grammar = _level_items(ai.load_grammar_bank(), "_sess_grammar", None, "point")
    dialogue = _level_items(ai.load_dialogue_bank(), "_sess_dialogue", None, "id")
    reading = _level_items(ai.load_readings_bank(), "_sess_readings", None, "id")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("📗 單字", len(vocab))
    m2.metric("📐 文法", len(grammar))
    m3.metric("🗣️ 對話", len(dialogue))
    m4.metric("📚 閱讀／字幕", len(reading))

    t_v, t_g, t_d, t_r = st.tabs(["📗 單字", "📐 文法", "🗣️ 對話", "📚 閱讀／字幕"])
    with t_v:
        if not vocab:
            st.info("還沒有 AI 單字。到「📖 單字庫 → 🤖 AI 單字庫」按生成。")
        else:
            q = st.text_input("搜尋（日文／中文／諧音）", key="lib_vq").strip()
            words = sorted(vocab)
            if q:
                words = [w for w in words if q in w
                         or q in (vocab[w].get("meaning_zh") or "")
                         or q in (vocab[w].get("mnemonic") or "")]
            st.caption(f"共 {len(vocab)} 字　·　符合 {len(words)} 字（最多顯示 80）")
            for w in words[:80]:
                e = vocab[w]
                st.markdown(f"**{w}**　{e.get('kana','')}　— {e.get('meaning_zh','')}"
                            + (f"　📣 {e['mnemonic']}" if e.get("mnemonic") else ""))
    with t_g:
        if not grammar:
            st.info("還沒有 AI 文法。到「文法解說核心 → 🤖 AI 生成」建立。")
        for g in grammar:
            with st.expander(f"[{g.get('level','')}] {g.get('point','')}　—　{g.get('meaning','')}"):
                if g.get("usage"):
                    st.caption(f"💡 {g['usage']}")
                for ex in g.get("examples", []):
                    st.markdown(f"- {ex.get('jp','')}（{ex.get('zh','')}）")
    with t_d:
        if not dialogue:
            st.info("還沒有 AI 對話。到「🗣️ AI 生活對話」生成。")
        for d in dialogue:
            with st.expander(f"[{d.get('level','')}] {d.get('title','')}　{d.get('title_zh','')}"):
                for ln in d.get("lines", []):
                    st.markdown(f"**{ln.get('speaker','')}**：{ln.get('jp','')}（{ln.get('zh','')}）")
    with t_r:
        if not reading:
            st.info("還沒有 AI 閱讀。到「📚 AI 互動閱讀」或「🎬 影視字幕」生成。")
        for r in reading:
            with st.expander(f"[{r.get('level','')}] {r.get('title','')}　{r.get('title_zh','')}"):
                for s in r.get("sentences", []):
                    st.markdown(f"- {s.get('jp','')}（{s.get('zh','')}）")


def render_ai_sidebar() -> None:
    """側欄顯示 Gemini key 與 GitHub Token 狀態 + 一鍵測試。"""
    st.sidebar.divider()
    st.sidebar.markdown("### 🤖 AI 互動狀態")
    all_keys = ai.get_all_api_keys()
    exhausted = st.session_state.setdefault("_exhausted_keys", set())
    n_total = len(all_keys)
    n_avail = sum(1 for k in all_keys if k not in exhausted)
    if n_total:
        st.sidebar.caption(f"🔑 Gemini key：**{n_avail} / {n_total} 把可用**")
        if st.sidebar.button("🔍 測試所有金鑰", use_container_width=True):
            from google import genai
            from google.genai import types
            results = []
            with st.spinner(f"逐一測試 {n_total} 把 key…"):
                for i, key in enumerate(all_keys, 1):
                    try:
                        genai.Client(api_key=key).models.generate_content(
                            model="gemini-2.5-flash-lite", contents="hi",
                            config=types.GenerateContentConfig(max_output_tokens=10))
                        results.append((i, "✅", key[:8] + "…", ""))
                    except Exception as e:  # noqa: BLE001
                        em = str(e)
                        if any(h in em for h in ai._QUOTA_HINTS):
                            exhausted.add(key)
                            results.append((i, "⏰", key[:8] + "…", "今日配額用完"))
                        elif "API key not valid" in em or "API_KEY_INVALID" in em:
                            results.append((i, "❌", key[:8] + "…", "key 被拒"))
                        else:
                            results.append((i, "⚠️", key[:8] + "…", em[:30]))
            st.session_state["_key_test"] = results
        for i, tag, prefix, note in st.session_state.get("_key_test", []):
            st.sidebar.caption(f"{tag} #{i} `{prefix}` {note}")
        if exhausted and st.sidebar.button("🔄 重置耗盡標記", use_container_width=True):
            st.session_state["_exhausted_keys"] = set()
            st.session_state.pop("_key_test", None)
            st.rerun()
    else:
        st.sidebar.caption("⚪ 尚未偵測到 Gemini key")
    ghk = ai.get_github_token()
    st.sidebar.caption(f"🟢 GitHub Token `{ghk[:10]}…`" if ghk
                       else "⚪ GitHub Token 未設（無法自動推回）")


# ===========================================================================
# 💬 情境會話（三合一：範例短文 + AI 生活對話 + AI 情境心智圖）
# ===========================================================================
def _quiz_question(level: str, mode: str):
    """依題型產生一道測驗題。回傳 dict 或 None（資料不足）。"""
    vocab = data.load_vocab(level)
    grammar = data.load_grammar(level)
    if mode == "文法：意義→選文型":
        if len(grammar) < 2:
            return None
        target = random.choice(grammar)
        others = [g for g in grammar if g["point"] != target["point"]]
        sample = random.sample(others, k=min(3, len(others)))
        options = [target["point"]] + [g["point"] for g in sample]
        random.shuffle(options)
        return {"prompt": target["meaning"], "answer": target["point"],
                "options": options, "hint": "選出符合語意的文型",
                "nonce": random.randint(0, 10**9)}
    if len(vocab) < 2:
        return None
    target = random.choice(vocab)
    others = [w for w in vocab if w["kanji"] != target["kanji"]]
    sample = random.sample(others, k=min(3, len(others)))
    if mode == "中文→選假名":
        options = [target["kana"]] + [w["kana"] for w in sample]
        prompt, answer, hint = target["chinese"], target["kana"], "選出正確的假名唸法"
    else:  # 日文→選中文
        options = [target["chinese"]] + [w["chinese"] for w in sample]
        prompt = f"{target['kanji']}（{target['kana']}）"
        answer, hint = target["chinese"], "選出正確的中文意思"
    random.shuffle(options)
    return {"prompt": prompt, "answer": answer, "options": options,
            "hint": hint, "nonce": random.randint(0, 10**9)}


def page_quiz(level: str) -> None:
    """測驗練習：三種主動回憶題型（中→假名／日→中／文法）。"""
    st.header(f"📝 {data.LEVELS[level]['label']} 測驗練習")
    st.caption("主動回憶練習：先想答案再作答。三種題型可切換，分數即時記錄。")

    mode = st.radio("題型", ["中文→選假名", "日文→選中文", "文法：意義→選文型"],
                    horizontal=True, key=f"quizmode_{level}")
    qkey = f"quizq_{level}_{mode}"
    if not st.session_state.get(qkey):
        st.session_state[qkey] = _quiz_question(level, mode)
    q = st.session_state[qkey]
    if not q:
        st.info("此級別／題型的資料不足，無法出題。")
        return

    st.markdown(f"**{q['hint']}**")
    st.markdown(f"## {q['prompt']}")
    choice = st.radio("選擇答案：", q["options"], index=None,
                      key=f"quizchoice_{level}_{q['nonce']}")
    c1, c2 = st.columns(2)
    if c1.button("送出答案", key=f"quizsubmit_{level}_{q['nonce']}"):
        stats = st.session_state.quiz[level]
        stats["total"] += 1
        if choice == q["answer"]:
            stats["correct"] += 1
            st.success("正解！🎉")
        else:
            st.error(f"再加油！正確答案是：{q['answer']}")
    if c2.button("下一題 ➡️", key=f"quiznext_{level}_{q['nonce']}"):
        st.session_state[qkey] = _quiz_question(level, mode)
        st.rerun()

    stats = st.session_state.quiz[level]
    if stats["total"]:
        st.caption(f"本級別測驗紀錄：答對 {stats['correct']} / {stats['total']} 題"
                   f"（正確率 {stats['correct'] / stats['total']:.0%}）")


def page_scenario(level: str) -> None:
    """整合原「情境短文／AI 情境生成／AI 生活對話／AI 互動閱讀」四個重複功能為單一入口。

    以分頁呈現：免金鑰的靜態範例短文打底，AI 對話、情境心智圖與互動閱讀
    為可選擴充（需 Gemini 金鑰）。四者皆屬「同一情境學習」，合併後介面更乾淨。
    """
    st.header(f"💬 {data.LEVELS[level]['label']} 情境會話")
    st.caption("同一情境的多種學法：先讀範例短文打底，再用 AI 依主題生成生活對話、情境心智圖或互動閱讀。")

    tab_passage, tab_dialogue, tab_mindmap, tab_reading = st.tabs(
        ["📄 範例短文（免金鑰）", "🗣️ AI 生活對話", "🤖 AI 情境心智圖", "📚 AI 互動閱讀"]
    )
    with tab_passage:
        page_passage(level)
    with tab_dialogue:
        page_ai_dialogue(level)
    with tab_mindmap:
        page_ai_generate(level)
    with tab_reading:
        page_ai_reading(level)


# ===========================================================================
# 主程式
# ===========================================================================
def main() -> None:
    st.set_page_config(page_title="JLPT 日文學習 App", page_icon="🇯🇵", layout="wide")
    init_state()

    # ---------------- Sidebar 第一層：選擇日檢級別 ----------------
    st.sidebar.title("🇯🇵 JLPT 日文學習")
    st.sidebar.markdown("### 第一層：選擇日檢級別")
    level = st.sidebar.selectbox(
        "日檢級別",
        options=data.LEVEL_ORDER,
        format_func=lambda lv: data.LEVELS[lv]["label"],
        key="selected_level",
    )

    meta = data.LEVELS[level]

    # ---------------- Sidebar 第二層：功能切換 ----------------
    st.sidebar.markdown("### 第二層：功能切換")

    # 50 音為基礎功能，僅在 N5 顯示；其餘級別隱藏，保持介面乾淨。
    functions = []
    if level == "N5":
        functions.append("50音")
    functions += ["📖 單字庫", "文法解說核心", "📝 測驗練習",
                  "🗣️ AI 生活對話", "🤖 AI 情境生成", "📚 AI 互動閱讀",
                  "🎬 影視字幕", "📚 我的資料庫", "🔁 複習"]

    feature = st.sidebar.radio("功能", functions, key=f"feature_{level}")

    # 側邊欄即時顯示各級別獨立進度
    st.sidebar.divider()
    st.sidebar.markdown("### 📊 各級別學習進度")
    for lv in data.LEVEL_ORDER:
        total = len(data.load_vocab(lv))
        done = learned_count(lv)
        mark = "👉 " if lv == level else ""
        st.sidebar.write(f"{mark}**{data.LEVELS[lv]['label']}**：{done} / {total} 字")
    st.sidebar.caption(f"🔁 待複習：{due_count()} 張")

    # AI 互動狀態（Gemini key / GitHub Token）
    render_ai_sidebar()

    # ---------------- 主頁面標題（依級別動態切換主題色）----------------
    st.markdown(
        f"<h1 style='color:{meta['color']}'>{meta['label']}</h1>",
        unsafe_allow_html=True,
    )
    st.caption(meta["desc"])
    st.divider()

    # ---------------- 功能分派（內容依級別動態切換）----------------
    if feature == "50音":
        page_gojuon(level)
    elif feature == "📖 單字庫":
        page_vocab_all(level)
    elif feature == "文法解說核心":
        page_grammar(level)
    elif feature == "📝 測驗練習":
        page_quiz(level)
    elif feature == "🗣️ AI 生活對話":
        page_ai_dialogue(level)
    elif feature == "🤖 AI 情境生成":
        page_ai_generate(level)
    elif feature == "📚 AI 互動閱讀":
        page_ai_reading(level)
    elif feature == "🎬 影視字幕":
        page_subtitles(level)
    elif feature == "📚 我的資料庫":
        page_library(level)
    elif feature == "🔁 複習":
        page_review()


if __name__ == "__main__":
    main()
