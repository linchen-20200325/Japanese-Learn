# STATE.md — 專案戰情室狀態

> 最後更新：2026-05-29
> 對應分支：`claude/jlpt-streamlit-n1-n5-Za8UK`

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
| `app.py` | Streamlit 主程式（UI／互動／狀態） | ✅ 已完成 |
| `data.py` | 資料存取層（從 `db/` 載入 JSON，含快取） | ✅ 已完成 |
| `db/N1.json`～`db/N5.json` | 各級別資料庫（單字／文法／短文／文章） | ✅ 已完成 |
| `db/gojuon.json` | 50 音資料庫（清音／濁音／半濁音／拗音） | ✅ 已完成 |
| `requirements.txt` | 相依套件（streamlit、gTTS） | ✅ 已完成 |
| `.gitignore` | 排除 `__pycache__`、`.pyc`、venv 等 | ✅ 已完成 |
| `CLAUDE.md` | 核心開發協議 v2.0 | ✅ 已完成 |
| `STATE.md` | 本戰情室文件 | ✅ 已完成 |

## 🗂️ 資料庫結構（db/）
- 每個級別一個 JSON 檔，內含三大區塊：
  - `vocab`：單字（`kanji/kana/romaji/chinese/pos/grammar/usage/examples`）。
  - `grammar`：文法（`point/meaning/usage/examples`）。
  - `passages`：短文與文章（`title/type/sentences[]`，每句含 `jp/kana/zh`）。
- `db/gojuon.json`：50 音四組（seion／dakuon／handakuon／yoon）。
- 未來可擴充為真正的外部資料庫或後台 API，`data.py` 介面不變。

## 📦 目前資料量
| 級別 | 單字 | 文法 | 短文/文章 |
|------|------|------|-----------|
| N5 | 12 | 6 | 3 |
| N4 | 10 | 6 | 3 |
| N3 | 10 | 6 | 3 |
| N2 | 10 | 6 | 3 |
| N1 | 10 | 6 | 3 |

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
