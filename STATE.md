# STATE.md — 專案戰情室狀態

> 最後更新：2026-05-29
> 對應分支：`claude/japanese-learning-ai-ieppd`

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
| `app.py` | Streamlit 主程式（UI／互動／狀態，10+ 功能頁） | ✅ 已完成 |
| `data.py` | 資料存取層（從 `db/` 載入 JSON，含 `lru_cache` 快取） | ✅ 已完成 |
| `db/N1.json`～`db/N5.json` | 各級別資料庫（單字／文法／短文／文章） | ✅ 已完成 |
| `db/gojuon.json` | 50 音資料庫（清音／濁音／半濁音／拗音） | ✅ 已完成 |
| `ai.py` | Gemini 互動層（情境/對話/閱讀/單字庫生成、GitHub 推回、key 輪轉） | ✅ 已完成 |
| `vocab_bank.json` | 大型日文單字庫（AI 生成，含假名／諧音／例句／JLPT 級別） | ✅ 種子 5 字 |
| `scripts/generate_vocab.py` | 本機批次生成腳本（讀詞表 → Gemini → 寫 vocab_bank.json） | ✅ 已完成 |
| `scripts/vocab_wordlist.txt` | JLPT 詞表（N5~N1 共 ~90 字，可擴充） | ✅ 已完成 |
| `requirements.txt` | 相依套件（streamlit、gTTS、google-genai） | ✅ 已完成 |
| `.gitignore` | 排除衍生檔 + `dashboard_data.json` | ✅ 已完成 |
| `CLAUDE.md` / `STATE.md` | 核心開發協議 / 本戰情室 | ✅ 已完成 |

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
### 資料層（jlpt 分支擴充）
- [x] 資料層改為 `db/` JSON 資料庫，`data.py` 負責載入（`lru_cache` 快取）。
- [x] 單字大幅擴充：每筆含詞性、核心文法、使用說明（怎麼用）與多組例句。
- [x] 例句／短文／文章皆含「唸法（假名）」與中文，可逐句發音。
- [x] 單字採「選到才顯示」中文與唸法（expander），符合記憶學習。
- [x] 文法解說含意義、用法與多組例句；情境短文升級為多篇（短文＋文章）。
- [x] 50音擴充為清音／濁音／半濁音／拗音四組（分頁呈現）。
- [x] 中翻日（選假名）進級小測驗，按級別獨立記錄正確率。

### AI 互動與學習（本分支新增，follow 英文版）
- [x] **🤖 AI 情境生成**：Gemini → 對話心智圖（mermaid）+ 句卡（日文／假名／羅馬拼音／中文／文法／台味諧音），依 JLPT 級別調整。
- [x] **🗣️ AI 生活對話**：Gemini → 6–10 句雙語對話 + 文法重點，每句 gTTS 發音，可整段加入複習。
- [x] **📚 AI 互動閱讀**：Gemini → 依主題/書籍生成日文短文（整句假名／中文／重點單字／文法），每句發音，可加入複習。
- [x] **📖 單字庫**：AI 雲端即時生成、JSON 下載、GitHub 自動推回、搜尋分頁；多 key 輪轉、配額耗盡偵測。
- [x] **🃏 單字卡**：翻面學習（核心單字 ∪ 單字庫同級別字），gTTS 發音 + 諧音。
- [x] **🔁 複習**：SM-2 簡化版 SRS，三鈕（忘記／普通／簡單），全級別共用。
- [x] 複習卡與已存課程持久化至 `dashboard_data.json`（已 gitignore）。
- [x] AppTest 全頁面 + 互動流程（翻面／生成解析／存課／加入複習／SRS 評分）通過。

## 📌 待辦事項 (TODO)
- [ ] 持續擴充各級別單字／文法／文章數量、`scripts/vocab_wordlist.txt` 至正版詞表。
- [ ] session_state 進度持久化（單字學會狀態目前重整會重置）。
- [ ] 測驗模式多樣化（日翻中、聽力選擇、文法填空）。
- [ ] 加入單元測試（pytest）覆蓋 `data.py` / `ai.py` 解析函式與資料完整性。

## 🐞 已知 Bug / 注意事項
- gTTS 與 Gemini 皆需網路；離線時語音自動停用、AI 頁顯示金鑰引導（優雅降級）。
- AI 互動需設 `GEMINI_API_KEY`（單把或 `GEMINI_API_KEYS` 多把輪轉）；自動推回需 `GITHUB_TOKEN`。
- `st.session_state` 學會進度為記憶體級，重整瀏覽器即清空（複習卡已持久化）。
- Streamlit Cloud 檔案系統為暫存：`dashboard_data.json` 與未推回的 `vocab_bank.json` 重新部署後會重置（UI 已提醒手動下載 / 推回保存）。
