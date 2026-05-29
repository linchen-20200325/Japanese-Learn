# -*- coding: utf-8 -*-
"""
app.py — JLPT 全階段日文學習 App（N1 ~ N5）

特色：
    • Sidebar 兩層導覽：先選級別，再切換功能。
    • 50 音僅在「N5 基礎」顯示，其餘級別自動隱藏，保持介面乾淨。
    • 每個級別擁有獨立的學習進度（st.session_state 不互相覆蓋）。
    • gTTS 採記憶體級播放（BytesIO），避免實體檔案鎖定（File Lock）。

執行方式：
    pip install -r requirements.txt
    streamlit run app.py
"""

from io import BytesIO

import streamlit as st

import data

# gTTS 為選用相依套件；若未安裝則優雅降級（停用語音，不中斷程式）。
try:
    from gtts import gTTS

    _GTTS_AVAILABLE = True
except Exception:  # pragma: no cover - 環境無網路 / 未安裝
    _GTTS_AVAILABLE = False


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


def play_button(text: str, key: str) -> None:
    """渲染一個發音按鈕；按下後於記憶體中合成並播放。"""
    if not _GTTS_AVAILABLE:
        st.caption("🔇 語音功能需安裝 gTTS 並連線網路")
        return

    if st.button("🔊 發音", key=key):
        try:
            audio_bytes = synthesize_speech(text)
            st.audio(audio_bytes, format="audio/mp3")
        except Exception as exc:  # 網路或服務暫時不可用
            st.warning(f"語音合成失敗（請檢查網路）：{exc}")


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


def mark_learned(level: str, kanji: str) -> None:
    """將某單字標記為已學會（記錄於該級別）。"""
    st.session_state.progress[level].add(kanji)


def learned_count(level: str) -> int:
    return len(st.session_state.progress[level])


# ===========================================================================
# 各功能頁面
# ===========================================================================
def page_gojuon(level: str) -> None:
    """50 音（基礎，僅 N5）。"""
    st.header("🈁 50 音入門")
    st.write("日文的基礎發音表，建議先熟練清音再進入單字學習。")

    gojuon = data.load_gojuon()
    cols_per_row = 5
    for i in range(0, len(gojuon), cols_per_row):
        cols = st.columns(cols_per_row)
        for col, item in zip(cols, gojuon[i : i + cols_per_row]):
            with col:
                st.markdown(
                    f"<div style='text-align:center;font-size:2rem;"
                    f"line-height:1.2'>{item['kana']}</div>"
                    f"<div style='text-align:center;color:#888'>{item['romaji']}</div>",
                    unsafe_allow_html=True,
                )
                play_button(item["kana"], key=f"goj_{item['romaji']}")


def page_vocab(level: str) -> None:
    """核心單字庫（依級別動態切換）。"""
    st.header(f"📚 {data.LEVELS[level]['label']} 核心單字庫")

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
            top, btn = st.columns([4, 1])
            with top:
                st.subheader(f"{word['kanji']}　{'✅' if done else ''}")
                st.markdown(
                    f"**假名：** {word['kana']}　|　**羅馬拼音：** {word['romaji']}"
                )
                st.markdown(f"**中文：** {word['chinese']}")
                st.caption(f"📝 核心文法：{word['grammar']}")
            with btn:
                play_button(word["kanji"], key=f"vocab_{level}_{idx}")
                if st.button(
                    "已學會" if not done else "↩️ 取消",
                    key=f"learn_{level}_{idx}",
                ):
                    if done:
                        learned.discard(word["kanji"])
                    else:
                        mark_learned(level, word["kanji"])
                    st.rerun()


def page_grammar(level: str) -> None:
    """文法解說核心（依級別動態切換）。"""
    st.header(f"📖 {data.LEVELS[level]['label']} 文法解說核心")

    grammar = data.load_grammar(level)
    if not grammar:
        st.info("此級別尚無文法資料。")
        return

    for idx, g in enumerate(grammar):
        with st.expander(f"{g['point']}　—　{g['meaning']}", expanded=(idx == 0)):
            st.markdown(f"**例句：** {g['example']}")
            st.markdown(f"**中譯：** {g['example_zh']}")
            play_button(g["example"], key=f"gram_{level}_{idx}")


def page_passage(level: str) -> None:
    """情境短文與進級（含小測驗，依級別動態切換）。"""
    st.header(f"📝 {data.LEVELS[level]['label']} 情境短文與進級")

    passage = data.load_passage(level)
    if not passage.get("japanese"):
        st.info("此級別尚無短文資料。")
        return

    st.subheader(passage["title"])
    with st.container(border=True):
        st.markdown(f"### {passage['japanese']}")
        play_button(passage["japanese"], key=f"passage_{level}")
        with st.expander("顯示中文翻譯"):
            st.write(passage["chinese"])

    st.divider()
    _vocab_quiz(level)


def _vocab_quiz(level: str) -> None:
    """以本級別單字產生「中翻日（選假名）」小測驗。"""
    st.subheader("🎯 進級小測驗")
    vocab = data.load_vocab(level)
    if len(vocab) < 2:
        st.info("單字不足，無法產生測驗。")
        return

    import random

    quiz_key = f"current_quiz_{level}"
    # 為每個級別維持一題當前題目，切換級別不互相干擾。
    if quiz_key not in st.session_state:
        st.session_state[quiz_key] = _new_question(level, vocab, random)

    q = st.session_state[quiz_key]
    st.write(f"請問「**{q['prompt']}**」的正確假名是？")

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
            st.session_state[quiz_key] = _new_question(level, vocab, random)
            st.rerun()

    stats = st.session_state.quiz[level]
    if stats["total"]:
        st.caption(
            f"本級別測驗紀錄：答對 {stats['correct']} / {stats['total']} 題"
            f"（正確率 {stats['correct'] / stats['total']:.0%}）"
        )


def _new_question(level: str, vocab: list, random_mod) -> dict:
    """產生一道測驗題（中文 → 選假名）。"""
    target = random_mod.choice(vocab)
    distractors = [w for w in vocab if w["kanji"] != target["kanji"]]
    sample = random_mod.sample(distractors, k=min(3, len(distractors)))
    options = [target["kana"]] + [w["kana"] for w in sample]
    random_mod.shuffle(options)
    return {
        "prompt": target["chinese"],
        "answer": target["kana"],
        "options": options,
        "nonce": random_mod.randint(0, 10**9),
    }


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
    functions += ["核心單字庫", "文法解說核心", "情境短文與進級"]

    feature = st.sidebar.radio("功能", functions, key=f"feature_{level}")

    # 側邊欄即時顯示各級別獨立進度
    st.sidebar.divider()
    st.sidebar.markdown("### 📊 各級別學習進度")
    for lv in data.LEVEL_ORDER:
        total = len(data.load_vocab(lv))
        done = learned_count(lv)
        mark = "👉 " if lv == level else ""
        st.sidebar.write(f"{mark}**{data.LEVELS[lv]['label']}**：{done} / {total} 字")

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
    elif feature == "核心單字庫":
        page_vocab(level)
    elif feature == "文法解說核心":
        page_grammar(level)
    elif feature == "情境短文與進級":
        page_passage(level)


if __name__ == "__main__":
    main()
