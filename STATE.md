# STATE.md — 專案戰情室狀態

> 最後更新：2026-05-29
> 對應分支：`claude/affectionate-bardeen-wMVbS`

---

## 🌐 當前環境
- Python 3.11+ / Streamlit / gTTS
- 啟動方式：
  ```bash
  pip install -r requirements.txt
  streamlit run app.py
  ```

## 📁 核心檔案
| 檔案 | 角色 | 狀態 |
|------|------|------|
| `app.py` | Streamlit 主程式（7 功能：50音／核心單字庫／單字卡／文法／💬情境會話／AI互動閱讀／單字庫／複習） | ✅ 已完成 |
| `ai.py` | Gemini 互動層（多金鑰輪轉、主題式生成、vocab_bank 讀寫與 GitHub 推回） | ✅ 已完成 |
| `data.py` | 資料存取層（從 `db/` 載入 JSON，含快取） | ✅ 已完成 |
| `db/N1.json`～`db/N5.json` | 各級別資料庫（單字／文法／短文／文章） | ✅ 已完成 |
| `db/gojuon.json` | 50 音資料庫（清音／濁音／半濁音／拗音） | ✅ 已完成 |
| `vocab_bank.json` | AI 生成的大單字庫（Gemini 批次生成，可推回 repo 永久保存） | ✅ 已完成 |
| `scripts/generate_vocab.py` | 本機批次生成單字（讀 `vocab_wordlist.txt`） | ✅ 已完成 |
| `requirements.txt` | 相依套件（streamlit、gTTS、google-genai） | ✅ 已完成 |
| `CLAUDE.md` / `STATE.md` | 開發協議 / 本戰情室 | ✅ 已完成 |

## 🔀 本次整併（以最新版 AI App 為底）
- **三合一**：原「情境短文與進級／🤖 AI 情境生成／🗣️ AI 生活對話」三個重複功能，
  合併為單一「💬 情境會話」（`page_scenario`），底下分頁：📄 範例短文（免金鑰）／🗣️ AI 生活對話／🤖 AI 情境心智圖。
- **修正「資料庫不會更新」bug**：AI 生成單字推回 GitHub 成功後，原本只清 `live_bank`、
  未寫回本機 `vocab_bank.json`，導致畫面停在舊字數。現於 `_record_push` 推回成功時
  同步寫回本機並清快取，字數即時更新（與英文版同因同修）。
- **核心單字擴充**：N5 12→24、N4 10→24、N3 10→22（保留並沿用）。
- 主題式生成已內建於 `ai.py`（`gen_dialogue` / `gen_reading` / `generate_material`），
  多把 Gemini 金鑰自動輪轉，金鑰請貼到 Streamlit Cloud → Settings → Secrets（勿入 repo）。

## 🗂️ 資料庫結構（db/）
- 每個級別一個 JSON 檔，內含三大區塊：
  - `vocab`：單字（`kanji/kana/romaji/chinese/pos/grammar/usage/examples`）。
  - `grammar`：文法（`point/meaning/usage/examples`）。
  - `passages`：短文與文章（`title/type/sentences[]`，每句含 `jp/kana/zh`）。
- `db/gojuon.json`：50 音四組（seion／dakuon／handakuon／yoon）。
- 未來可擴充為真正的外部資料庫或後台 API，`data.py` 介面不變。

## 📦 目前資料量（核心 db）
| 級別 | 單字 | 文法 | 短文/文章 |
|------|------|------|-----------|
| N5 | 24 | 6 | 3 |
| N4 | 24 | 6 | 3 |
| N3 | 22 | 6 | 3 |
| N2 | 22 | 6 | 3 |
| N1 | 22 | 6 | 3 |

> 另有 `vocab_bank.json`（AI 生成）可無上限擴充：App 內「📖 單字庫」按「開始生成」，
> 或本機跑 `python scripts/generate_vocab.py`。

## ✅ 已完成進度
- [x] 資料層改為 `db/` JSON 資料庫，`data.py` 負責載入（`lru_cache` 快取）。
- [x] 單字大幅擴充：每筆含詞性、核心文法、使用說明（怎麼用）與多組例句。
- [x] 例句／短文／文章皆含「唸法（假名）」與中文，可逐句發音。
- [x] 單字採「選到才顯示」中文與唸法（expander），符合記憶學習。
- [x] 文法解說含意義、用法與多組例句。
- [x] 情境短文升級為多篇（短文＋文章），可整篇朗讀或逐句顯示。
- [x] 50音擴充為清音／濁音／半濁音／拗音四組（分頁呈現）。
- [x] 各級別獨立進度（單字學習 + 測驗統計），互不覆蓋。
- [x] gTTS 記憶體級（BytesIO）合成，`st.cache_data` 快取，未安裝時優雅降級。
- [x] 中翻日（選假名）進級小測驗，按級別獨立記錄正確率。

## 📌 待辦事項 (TODO)
- [ ] 持續擴充各級別單字／文法／文章數量。
- [ ] 進度持久化（目前重整頁面後 session_state 會重置）。
- [ ] 單字加入標籤／搜尋與收藏（我的最愛）功能。
- [ ] 測驗模式多樣化（日翻中、聽力選擇、文法填空）。
- [ ] 加入單元測試（pytest）覆蓋 `data.py` 載入函式與資料完整性。

## 🐞 已知 Bug / 注意事項
- gTTS 需網路連線；離線環境下語音按鈕會自動停用（已優雅降級，非錯誤）。
- `st.session_state` 為記憶體級，**重新整理瀏覽器即清空進度**（尚未持久化）。
- 測驗的干擾選項取自同級別單字；某級別單字 < 2 筆會停用測驗（目前皆 ≥ 10 筆）。
