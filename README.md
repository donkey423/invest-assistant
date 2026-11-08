# 投資情報小助手

每天自動抓台股、全球股市、美國 AI 股與財經新聞，由 Claude 整理成一頁早報。

- 早報網頁：`site/`（純 HTML/CSS/JS，GitHub Pages 直接架）
- 產生早報：`python -m briefing`，結果寫到 `site/data/latest.json`，並另存一份到 `site/data/archive/`
- 排程：`.github/workflows/briefing.yml`，週一到週五台灣時間 07:30（寄 Email）、12:00、14:00、22:00

## 第一次設定（約 10 分鐘）

1. 把這個資料夾推上你的 GitHub repo（可以是私人 repo）。
2. `Settings` → `Secrets and variables` → `Actions`：
   - Secrets：`ANTHROPIC_API_KEY`（必填）、`EMAIL_SENDER`（你的 Gmail）、`EMAIL_PASSWORD`（Gmail 應用程式密碼）、`EMAIL_RECEIVERS`（可不填，預設寄給自己）
   - LINE 推播（可不填 = 不推 LINE）：`LINE_CHANNEL_TOKEN`、`LINE_TO`。申請步驟見 [alerts/README.md](alerts/README.md)
   - Variables：`CLAUDE_MODEL`（不填 = `claude-opus-5-5`；想省錢填 `claude-sonnet-5-5`）、`SITE_URL`（網站開好後填，Email 裡會放連結）
3. `Settings` → `Pages` → Source 選 `GitHub Actions`。
4. `Actions` → `產生早報` → `Run workflow`，第一次可以勾「寄 Email」測試。

私人 repo 的 GitHub Pages 需要付費方案；免費帳號請把 repo 設為公開（持股資料在 `.gitignore` 裡，不會上傳）。

## 在自己電腦預覽

```bash
pip install -r requirements.txt
python tools/make_sample.py          # 沒網路或沒 API key 時，產生假資料預覽
python -m briefing                   # 有 ANTHROPIC_API_KEY 時，產生真的早報
cd site && python -m http.server 8000   # 打開 http://localhost:8000
```

## 改追蹤的項目

指數、AI 股清單、新聞來源，以及「今天的世界」地圖的地區與關鍵字（`REGIONS`、`RISK_WORDS`、`AI_WORDS`）都在 `briefing/config.py`。
價格／事件警報的條件在 `alerts/rules.json`，說明見 [alerts/README.md](alerts/README.md)。

## 產業鏈訊號

網頁的「產業鏈訊號」分頁涵蓋 30 條產業鏈（半導體、AI 與資料中心、電子零組件、消費電子、車用與能源、傳產與原物料、金融、生技等），每條分三層看：① 上游訊號（報價、韓國出口、雲端資本支出）② 台股月營收（證交所／櫃買中心 openapi，免費）③ 代表股股價已經反映多少。燈號只說明基本面往哪個方向變，不是買賣建議。

- 鏈與代表股：`briefing/config.py` 的 `CHAINS`；月營收提醒額外追蹤的台股：`REVENUE_WATCH`
- 上游訊號：原油、銅、鋼價、穀物、美債殖利率由 Yahoo 自動抓（`CHAINS` 的 `market`）；報價、運價、出口、資本支出等手動填在 `site/data/chain_inputs.json`（附來源與日期，沒資料的標「待更新」）
- 月營收提醒（預設推由負轉正、由正轉負、創新高；加速／放緩只在網頁顯示）：`alerts/rules.json` 的 `revenue`，跟著警報排程推 LINE／Email
- 訊號回測：每個交易日把燈號與代表股價格記在 `site/data/signal_log.json`，網頁顯示燈號亮起後 1 週、1 個月、3 個月的平均超額報酬與命中率（`briefing/backtest.py`）
- AI 早報的「主題推理」由雲端排程寫在 `ai_summary.json` 的 `themes`，規則見 [docs/ai-routine.md](docs/ai-routine.md)

## 我的資產（持股明細與分析）

想在手機上新增持股：持股存在你自己的 Supabase（有登入保護），設定步驟見 [supabase/README.md](supabase/README.md)。
只想在自己電腦用：持股放在 `private/`，不會上傳 GitHub，見 [holdings/README.md](holdings/README.md)。

## 不用 API key：用你的 Claude 帳號寫 AI 摘要

每個交易日 07:47（台灣時間）有一個雲端排程用你的 Claude 帳號讀當天資料，寫出 `site/data/ai_summary.json` 推回這個 repo，接著 GitHub Actions 自動重新產生早報並寄 Email。工作步驟寫在 [docs/ai-routine.md](docs/ai-routine.md)。這份摘要會用到當天傍晚，22:00 那次回到免費模式。有設 `ANTHROPIC_API_KEY` 的話，以 API 為準。

## 原則

- 數字一律由程式計算，Claude 只負責挑重點與寫說明，每則重點都附原文連結。
- 任何一步失敗都保留上一份內容並在頁面上提示，不會整頁壞掉。
- 內容僅供參考，不構成投資建議。

## 測試

```bash
python -m pytest
```

## 免費模式

沒有設定 ANTHROPIC_API_KEY 時，早報不呼叫 Claude：行情數字照常計算，重點改成各新聞來源輪流挑的最新標題（附原文連結），完全不花錢。設定 key 之後就自動改回 AI 摘要。

