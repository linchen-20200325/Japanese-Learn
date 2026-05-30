# STATE.md — 戰情室

## 專案
JLPT 日文學習 App（Streamlit + Gemini API + gTTS 發音）。部署：GitHub + Streamlit Cloud。

## 入口與分支
- 進入點：`app.py`　·　部署分支：`claude/jlpt-streamlit-n1-n5-Za8UK`

## 檔案結構（推導自檔名）
- `app.py`：主程式（UI／頁面／SRS／狀態，雙層導覽：級別 × 功能）
- `ai.py`：Gemini 互動層（多金鑰輪轉、生成、GitHub 推回）
- `data.py`：資料存取層（從 `db/` 載入，含 `lru_cache`）
- `db/N1~N5.json`、`db/gojuon.json`：內建單字／文法／短文／50音
- `vocab_bank.json`／`grammar_bank.json`／`dialogue_bank.json`／`readings_bank.json`：AI 生成累積庫（推 GitHub 永久保存）
- `scripts/generate_vocab.py`＋`vocab_wordlist.txt`：本機批次生成詞表
- `requirements.txt`：streamlit、gTTS、google-genai

## 功能（選單）
50音 / 📖 單字庫 / 文法解說核心 / 📝 測驗練習 / 🗣️ AI 生活對話 / 🤖 AI 情境生成 / 📚 AI 互動閱讀 / 🎬 影視字幕 / 📚 我的資料庫 / 🔁 複習

## 核心機制
生成 → session 疊加層（即時可見）→ 推 GitHub `*_bank.json`（只增不減累積）。金鑰存 Streamlit Secrets（`GEMINI_API_KEYS`／`GITHUB_TOKEN`）。

## 待辦
- （待指示）
