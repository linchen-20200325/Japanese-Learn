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
| `app.py` | Streamlit 主程式（UI／互動／狀態，7+ 功能頁） | ✅ 已完成 |
| `data.py` | 靜態資料層（N1~N5 單字／文法／短文／50音） | ✅ 已完成 |
| `ai.py` | Gemini 互動層（情境生成、單字庫生成、GitHub 推回、key 輪轉） | ✅ 已完成 |
| `vocab_bank.json` | 大型日文單字庫（AI 生成，含假名／諧音／例句／JLPT 級別） | ✅ 種子 5 字 |
| `scripts/generate_vocab.py` | 本機批次生成腳本（讀詞表 → Gemini → 寫 vocab_bank.json） | ✅ 已完成 |
| `scripts/vocab_wordlist.txt` | JLPT 詞表（N5~N1 共 ~90 字，可擴充） | ✅ 已完成 |
| `requirements.txt` | 相依套件（streamlit、gTTS、google-genai） | ✅ 已完成 |
| `.gitignore` | 排除衍生檔 + `dashboard_data.json` | ✅ 已完成 |
| `CLAUDE.md` / `STATE.md` | 核心開發協議 / 本戰情室 | ✅ 已完成 |

## ✅ 已完成進度
- [x] 資料層與 UI 層分離（`data.py` 靜態 + `ai.py` AI 互動 / `app.py` UI）。
- [x] N1~N5 全級別單字、文法、情境短文 + 50音（僅 N5）。
- [x] Sidebar 兩層導覽 + 主頁面依級別動態切換 + 級別主題色 + 待複習數。
- [x] 各級別獨立進度（單字 + 測驗統計），互不覆蓋。
- [x] gTTS 記憶體級合成（沿用），`st.cache_data` 快取，未安裝優雅降級。
- [x] **🤖 AI 情境生成**：Gemini → 對話心智圖（mermaid）+ 句卡（日文／假名／羅馬拼音／中文／文法／台味諧音），依 JLPT 級別調整。
- [x] **🗣️ AI 生活對話**：Gemini → 6–10 句雙語對話 + 文法重點，每句 gTTS 發音，可整段加入複習。
- [x] **📚 AI 互動閱讀**：Gemini → 依主題/書籍生成日文短文（整句假名／中文／重點單字／文法），每句發音，可加入複習。
- [x] **📖 單字庫**：AI 雲端即時生成、JSON 下載、GitHub 自動推回、搜尋分頁；多 key 輪轉、配額耗盡偵測。
- [x] **🃏 單字卡**：翻面學習（核心單字 ∪ 單字庫同級別字），gTTS 發音 + 諧音。
- [x] **🔁 複習**：SM-2 簡化版 SRS，三鈕（忘記／普通／簡單），全級別共用。
- [x] 複習卡與已存課程持久化至 `dashboard_data.json`（已 gitignore）。
- [x] AppTest 全頁面 + 互動流程（翻面／生成解析／存課／加入複習／SRS 評分）通過。

## 📌 待辦事項 (TODO)
- [ ] 擴充 `scripts/vocab_wordlist.txt` 至正版 JLPT 完整詞表。
- [ ] 50音加入濁音／半濁音／拗音表。
- [ ] 加入單元測試（pytest）覆蓋 `data.py` / `ai.py` 解析函式。

## 🐞 已知 Bug / 注意事項
- gTTS 與 Gemini 皆需網路；離線時語音自動停用、AI 頁顯示金鑰引導（優雅降級）。
- AI 互動需設 `GEMINI_API_KEY`（單把或 `GEMINI_API_KEYS` 多把輪轉）；自動推回需 `GITHUB_TOKEN`。
- Streamlit Cloud 檔案系統為暫存：`dashboard_data.json` 與未推回的 `vocab_bank.json` 重新部署後會重置（已在 UI 提醒手動下載 / 推回保存）。
