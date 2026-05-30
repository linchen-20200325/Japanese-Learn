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
- 生成 → session 疊加層（即時可見）→ 推 GitHub `*_bank.json`（只增不減累積）。金鑰存 Streamlit Secrets（`GEMINI_API_KEYS`／`GITHUB_TOKEN`）。
- 學習進度持久化：`progress`（已學會，各級別）／`quiz`（測驗統計）／`favorites`（收藏，跨級別）皆存 `dashboard_data.json`（gitignore，部署本機；Cloud 重新部署會重置）。
- 測驗 4 題型：中→假名、日→中、🔊聽發音→假名、文法意義→文型（`page_quiz`／`_quiz_question`）。
- 收藏：單字卡「☆收藏」→「📚 我的資料庫 → ⭐我的最愛」集中檢視。
- 內容量：db 各級單字 22–24、文法 11、短文 3；AI bank 持續長大（vocab_bank 已 600+）。手動擴充已足，後續靠 App 內 AI 生成。

## 待辦
- （待指示）

## 測試
- `pytest -q`：44 passed（`tests/test_data.py` 資料完整性 + `tests/test_ai.py` 純函式解析）。
- 跨部署永久化：「📚 我的資料庫 → ☁️ 備份／還原」手動推 GitHub `progress_backup.json`（還原採聯集）。
