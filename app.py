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

import datetime
import json
import random
from io import BytesIO

import streamlit as st

import data
import srs
import store

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
    if "srs_store" not in st.session_state:
        # SRS 間隔重複進度（跨級別），啟動時嘗試從本機 progress.json 載入
        st.session_state.srs_store = store.load_store()


def save_progress() -> None:
    """將 SRS 進度寫回本機（雲端暫存環境失敗時靜默忽略，改用匯出備份）。"""
    store.save_store(st.session_state.srs_store)


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
    st.write("日文的基礎發音表，建議先熟練清音，再進入濁音、半濁音與拗音。")

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
                for col, item in zip(cols, rows[i : i + cols_per_row]):
                    with col:
                        st.markdown(
                            f"<div style='text-align:center;font-size:2rem;"
                            f"line-height:1.2'>{item['kana']}</div>"
                            f"<div style='text-align:center;color:#888'>"
                            f"{item['romaji']}</div>",
                            unsafe_allow_html=True,
                        )
                        play_button(item["kana"], key=f"goj_{key}_{item['romaji']}")


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


def page_grammar(level: str) -> None:
    """文法解說核心（依級別動態切換）。"""
    st.header(f"📖 {data.LEVELS[level]['label']} 文法解說核心")
    st.caption("每個文法皆含意義、用法說明與多組例句（可顯示唸法與中文）。")

    grammar = data.load_grammar(level)
    if not grammar:
        st.info("此級別尚無文法資料。")
        return

    for idx, g in enumerate(grammar):
        with st.expander(f"{g['point']}　—　{g['meaning']}", expanded=(idx == 0)):
            st.markdown(f"**意義：** {g['meaning']}")
            if g.get("usage"):
                st.success(f"💡 用法：{g['usage']}")
            render_examples(g.get("examples", []), key_prefix=f"gram_{level}_{idx}")


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
# 📊 學習儀表板（科學學習監督：跨級別總覽）
# ===========================================================================
def page_dashboard(level: str) -> None:
    st.header("📊 學習儀表板")
    st.caption("以間隔重複（SRS）追蹤記憶狀態：今日待複習、保留率、連續天數與掌握度分布。")

    s = st.session_state.srs_store
    ov = store.overall_stats(s)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("🔥 連續天數", f"{ov['streak']} 天")
    c2.metric("📅 今日待複習", f"{ov['due_today']} 張")
    c3.metric("✅ 已學卡片", f"{ov['studied']} / {ov['catalog_total']}")
    ret = ov["retention"]
    c4.metric("🧠 記憶保留率", "—" if ret is None else f"{ret:.0%}")

    st.divider()

    # 掌握度分布
    st.subheader("🎯 掌握度分布")
    m = ov["mastery"]
    labels = {"new": "🆕 未學", "learning": "📖 學習中",
              "young": "🌱 漸熟", "mature": "🌳 已掌握"}
    cols = st.columns(4)
    for col, key in zip(cols, ["new", "learning", "young", "mature"]):
        col.metric(labels[key], m.get(key, 0))

    # 未來 7 天複習預測
    st.subheader("📈 未來 7 天複習預測")
    fc = srs.forecast(list(s["cards"].values()), days=7)
    today = datetime.date.today()
    day_labels = [(today + datetime.timedelta(days=i)).strftime("%m/%d")
                  for i in range(7)]
    st.bar_chart({"到期張數": dict(zip(day_labels, fc))})

    # 各級別進度條
    st.subheader("📚 各級別掌握進度")
    for lv in data.LEVEL_ORDER:
        ls = store.level_stats(s, lv)
        mastered = ls["young"] + ls["mature"]
        total = ls["total"] or 1
        st.write(
            f"**{data.LEVELS[lv]['label']}**："
            f"已學 {ls['studied']}／{ls['total']}　|　"
            f"熟練 {mastered}　|　今日到期 {ls['due']}"
        )
        st.progress(mastered / total)

    st.divider()
    _backup_controls()


def _backup_controls() -> None:
    """進度備份：雲端檔案系統為暫存，提供匯出／匯入 JSON 以長期保存。"""
    st.subheader("💾 進度備份（雲端必備）")
    st.caption("Streamlit Cloud 重新部署後檔案會重置，請定期下載備份，換裝置時再上傳還原。")
    col_dl, col_up = st.columns(2)
    with col_dl:
        st.download_button(
            "⬇️ 下載進度備份",
            data=json.dumps(st.session_state.srs_store, ensure_ascii=False, indent=2),
            file_name="jlpt_progress.json",
            mime="application/json",
        )
    with col_up:
        uploaded = st.file_uploader("⬆️ 上傳進度還原", type="json", key="restore")
        if uploaded is not None:
            try:
                loaded = json.load(uploaded)
                base = store.default_store()
                base.update(loaded)
                st.session_state.srs_store = base
                save_progress()
                st.success("進度已還原！")
            except (json.JSONDecodeError, ValueError):
                st.error("檔案格式錯誤，無法還原。")


# ===========================================================================
# 🔁 智慧複習（SRS：主動回憶 + 間隔重複）
# ===========================================================================
def page_review(level: str) -> None:
    st.header(f"🔁 {data.LEVELS[level]['label']} 智慧複習")
    st.caption("先回想答案，再翻面評分。系統依間隔重複演算法安排下次出現時間。")

    s = st.session_state.srs_store

    # 設定：今日新卡上限
    new_limit = st.slider("今日新卡上限", 0, 30, 10, key=f"newlim_{level}",
                          help="控制每天引入的新單字／文法量，避免負擔過重。")

    # 建立本級別的候選卡：單字 + 文法
    catalog = store.build_all_cards()
    level_ids = [(cid, meta) for cid, meta in catalog.items() if meta["level"] == level]
    # 取得目前排程狀態的卡片清單（含尚未建立的視為新卡）
    candidate_cards = []
    for cid, meta in level_ids:
        card = s["cards"].get(cid) or srs.new_card(cid, meta["type"], level)
        candidate_cards.append(card)

    session = srs.build_session(candidate_cards, new_limit=new_limit, review_limit=50)

    if not session:
        st.success("🎉 太棒了！本級別目前沒有到期的複習卡。明天再來吧！")
        return

    # 目前卡片指標（以 session_state 記住位置）
    pos_key = f"review_pos_{level}"
    flip_key = f"review_flip_{level}"
    if pos_key not in st.session_state:
        st.session_state[pos_key] = 0
    if st.session_state[pos_key] >= len(session):
        st.session_state[pos_key] = 0

    idx = st.session_state[pos_key]
    card = session[idx]
    meta = catalog[card["id"]]
    payload = meta["payload"]

    st.progress((idx) / len(session), text=f"本回合進度 {idx} / {len(session)}")

    badge = "🆕 新卡" if srs.is_new(card) else f"複習第 {card['reviews']+1} 次"
    st.caption(f"{badge}　|　類型：{'單字' if meta['type']=='vocab' else '文法'}")

    with st.container(border=True):
        if meta["type"] == "vocab":
            st.markdown(f"## {payload['kanji']}")
            play_button(payload["kanji"], key=f"rev_play_{level}_{idx}")
        else:
            st.markdown(f"## {payload['point']}")

        if not st.session_state.get(flip_key, False):
            if st.button("🔄 翻面看答案", key=f"flip_{level}_{idx}", use_container_width=True):
                st.session_state[flip_key] = True
                st.rerun()
        else:
            if meta["type"] == "vocab":
                st.markdown(f"**唸法：** {payload['kana']}　|　**羅馬拼音：** {payload['romaji']}")
                st.markdown(f"**中文：** {payload['chinese']}")
                if payload.get("usage"):
                    st.success(f"💡 {payload['usage']}")
                render_examples(payload.get("examples", [])[:1], key_prefix=f"rev_{level}_{idx}")
            else:
                st.markdown(f"**意義：** {payload['meaning']}")
                if payload.get("usage"):
                    st.success(f"💡 {payload['usage']}")
                render_examples(payload.get("examples", [])[:1], key_prefix=f"rev_{level}_{idx}")

            st.markdown("**這張卡你記得多清楚？**")
            b1, b2, b3 = st.columns(3)
            if b1.button("😣 忘記", key=f"again_{level}_{idx}", use_container_width=True):
                _do_grade(card, srs.AGAIN, level)
            if b2.button("🙂 普通", key=f"good_{level}_{idx}", use_container_width=True):
                _do_grade(card, srs.GOOD, level)
            if b3.button("😎 簡單", key=f"easy_{level}_{idx}", use_container_width=True):
                _do_grade(card, srs.EASY, level)


def _do_grade(card: dict, quality: int, level: str) -> None:
    """評分後更新排程、推進到下一張、存檔。"""
    meta = store.build_all_cards()[card["id"]]
    store.review_card(st.session_state.srs_store, card["id"], meta["type"], level, quality)
    save_progress()
    st.session_state[f"review_pos_{level}"] += 1
    st.session_state[f"review_flip_{level}"] = False
    st.rerun()


# ===========================================================================
# 📰 分級閱讀（真正的閱讀素材 + 閱讀理解）
# ===========================================================================
def page_reading(level: str) -> None:
    st.header(f"📰 {data.LEVELS[level]['label']} 分級閱讀")
    st.caption("循序漸進的閱讀文章，逐句可顯示假名與中文，讀完做閱讀理解測驗。")

    articles = data.load_reading(level)
    if not articles:
        st.info("此級別的分級閱讀文章尚在擴充中。")
        return

    titles = [f"{a['title']}（{a.get('title_zh','')}・約{a.get('minutes','?')}分）" for a in articles]
    choice = st.radio("選擇文章：", titles, key=f"reading_pick_{level}")
    article = articles[titles.index(choice)]

    st.subheader(article["title"])
    full_text = "".join(s["jp"] for s in article.get("sentences", []))
    play_button(full_text, key=f"reading_full_{level}", label="🔊 整篇朗讀")

    show_aid = st.toggle("顯示假名與中文（建議先不開，挑戰盲讀）", key=f"reading_aid_{level}")

    for i, sent in enumerate(article.get("sentences", [])):
        with st.container(border=True):
            st.markdown(f"#### {sent['jp']}")
            cols = st.columns([1, 4])
            with cols[0]:
                play_button(sent["jp"], key=f"reading_{level}_{i}", label="🔊")
            if show_aid:
                st.caption(f"📖 {sent.get('kana','')}")
                st.caption(f"🇹🇼 {sent.get('zh','')}")
            else:
                with st.expander("看假名與中文"):
                    st.caption(f"📖 {sent.get('kana','')}")
                    st.caption(f"🇹🇼 {sent.get('zh','')}")

    st.divider()
    _reading_quiz(article, level)


def _reading_quiz(article: dict, level: str) -> None:
    """閱讀理解測驗：依文章內容回答選擇題。"""
    questions = article.get("questions", [])
    if not questions:
        return
    st.subheader("🧩 閱讀理解測驗")
    with st.form(key=f"reading_quiz_{level}_{article['title']}"):
        answers = []
        for i, q in enumerate(questions):
            pick = st.radio(f"Q{i+1}. {q['q']}", q["options"],
                            key=f"rq_{level}_{i}", index=None)
            answers.append(pick)
        submitted = st.form_submit_button("送出作答")
    if submitted:
        correct = 0
        for i, q in enumerate(questions):
            if answers[i] == q["answer"]:
                correct += 1
                st.success(f"Q{i+1} ✅ 正解：{q['answer']}")
            else:
                st.error(f"Q{i+1} ❌ 正確答案：{q['answer']}")
            if q.get("explain"):
                st.caption(f"💡 {q['explain']}")
        st.info(f"得分：{correct} / {len(questions)}（{correct/len(questions):.0%}）")


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
    functions = ["📊 學習儀表板", "🔁 智慧複習"]
    if level == "N5":
        functions.append("50音")
    functions += ["核心單字庫", "文法解說核心", "情境短文與進級", "📰 分級閱讀"]

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
    if feature == "📊 學習儀表板":
        page_dashboard(level)
    elif feature == "🔁 智慧複習":
        page_review(level)
    elif feature == "50音":
        page_gojuon(level)
    elif feature == "核心單字庫":
        page_vocab(level)
    elif feature == "文法解說核心":
        page_grammar(level)
    elif feature == "情境短文與進級":
        page_passage(level)
    elif feature == "📰 分級閱讀":
        page_reading(level)


if __name__ == "__main__":
    main()
