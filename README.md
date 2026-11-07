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

指數、AI 股清單、新聞來源都在 `briefing/config.py`。
價格／事件警報的條件在 `alerts/rules.json`，說明見 [alerts/README.md](alerts/README.md)。

## 我的資產（持股明細與分析）

持股資料只放在你自己電腦的 `private/`，不會上傳 GitHub。設定與使用方式見 [holdings/README.md](holdings/README.md)。

## 原則

- 數字一律由程式計算，Claude 只負責挑重點與寫說明，每則重點都附原文連結。
- 任何一步失敗都保留上一份內容並在頁面上提示，不會整頁壞掉。
- 內容僅供參考，不構成投資建議。

## 測試

```bash
python -m pytest
```
