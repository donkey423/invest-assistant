# 推播與警報

## 會收到什麼
- **早報**：`python -m briefing --notify` 產生早報後，寄 Email 並推一則 LINE（標題、台股、全球股市、AI 股、財經重點）。
- **警報**：`.github/workflows/alerts.yml` 在台股與美股交易時段每 30 分鐘跑 `python -m alerts check`，條件成立才推播。
  同一檔同一種條件一天只通知一次；同一則新聞只通知一次；第一次執行不會把舊新聞全推出來。

## 改警報條件
只改 `alerts/rules.json`：
- `above` / `below`：漲破／跌破某價位
- `move_pct`：單日漲跌幅超過幾 %
- `new_52w`：創一年新高或新低
- `events[].keywords`：新聞標題含任一關鍵字就通知；關鍵字中間有空白代表兩個詞都要出現（例如 `台積電 營收`）

台股個股代號用 Yahoo 格式，例如台積電 `2330.TW`、櫃買股 `.TWO`。

## 設定 LINE（約 10 分鐘，一次就好）
LINE Notify 已在 2025 年停止服務，所以改用 LINE 官方帳號（免費方案每月 200 則推播，個人用夠）。
1. 到 LINE Developers（developers.line.biz）用你的 LINE 登入，建立 Provider，再建立一個 **Messaging API** channel。
2. 在 channel 的 Messaging API 頁籤，掃 QR code 把這個官方帳號加為好友。
3. 同一頁最下方按 **Issue** 產生 Channel access token（長期）。
4. 在 Basic settings 頁籤找到 **Your user ID**（U 開頭）。
5. 到 GitHub repo → Settings → Secrets and variables → Actions，新增：
   - `LINE_CHANNEL_TOKEN` = 第 3 步的 token
   - `LINE_TO` = 第 4 步的 user ID
Email 沿用早報的 `EMAIL_SENDER`、`EMAIL_PASSWORD`（Gmail 應用程式密碼）、`EMAIL_RECEIVERS`。沒設定的通道會自動略過。

## 本機試跑
```
python -m alerts brief --dry-run    # 印出 LINE 早報內容，不推送
python -m alerts check --dry-run    # 抓行情與新聞，印出會觸發的警報，不推送也不存狀態
```
