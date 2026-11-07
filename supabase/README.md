# 手機新增持股：Supabase 設定（約 10 分鐘，免費）

設好之後，打開網站的「我的資產」→ 用 Email 登入 → 就能在手機上新增、修改、刪除持股。
損益與分析每個交易日自動計算兩次（台灣時間 14:30 台股收盤後、05:30 美股收盤後）。

**安全性**：網站是公開的，但持股存在 Supabase 資料庫裡，並用 Row Level Security 鎖住：沒登入的人、或登入的其他人，都讀不到你的資料。網頁上只放「公開金鑰」，能改資料的「secret 金鑰」只放在 GitHub Secrets。

## 1. 準備 Supabase 專案

到 [supabase.com/dashboard](https://supabase.com/dashboard)。你已經有一個暫停中的專案 `donkey423's Project`（東京），按 **Restore project** 恢復就能用；或另外 New project 建一個新的（Region 選 Tokyo）。

> 免費專案一週沒有任何存取會自動暫停。設好後每天的自動計算會存取它，就不會再被暫停。

## 2. 建立資料表

左側 **SQL Editor** → New query → 把 [`schema.sql`](schema.sql) 整份貼上 → **Run**。看到 `Success. No rows returned` 就完成了。

## 3. 設定登入連結要回到哪裡

左側 **Authentication** → **URL Configuration**：

- **Site URL** 填你的網站網址，例如 `https://donkey423.github.io/invest-assistant/`
- **Redirect URLs** 也加上同一個網址

## 4. 把金鑰放到對的地方

左側 **Project Settings** → **API Keys**（與 **Data API** 頁的 Project URL）：

| 拿什麼 | 放哪裡 |
|---|---|
| Project URL（`https://xxxx.supabase.co`） | `site/supabase-config.js` 的 `url`，以及 GitHub Secret `SUPABASE_URL` |
| Publishable key（`sb_publishable_` 開頭） | `site/supabase-config.js` 的 `key`（公開沒關係） |
| Secret key（`sb_secret_` 開頭） | **只放** GitHub Secret `SUPABASE_SECRET_KEY`，絕對不要放進網站或 commit |

GitHub Secrets 在 repo 的 `Settings` → `Secrets and variables` → `Actions` → `New repository secret`。改好 `site/supabase-config.js` 後 commit 推上去，網站就會切換成登入模式。

## 5. 第一次登入，然後關掉註冊

1. 用手機打開網站 → 我的資產 → 輸入 Email → 寄登入連結 → **在同一支手機**打開信裡的連結。
2. 登入成功後，回 Supabase：**Authentication** → **Sign In / Providers** → 關掉 **Allow new users to sign up**。這樣別人就算找到網站也註冊不了。

> Supabase 內建的寄信服務每小時只能寄少量登入信，測試時別連按太多次。登入會保留在手機上，一般不需要常常重新登入。

## 6. 新增持股並算第一次

在手機上新增持股後，到 GitHub repo → `Actions` → `我的資產` → `Run workflow` 手動算第一次（也可以等排程）。之後重新整理網頁就會看到損益與分析。

沒有設定 `ANTHROPIC_API_KEY` 時只算數字，AI 健檢那塊會空著；之後想開再加這個 Secret 就好。

## 想換成自己的伺服器？

Python 端的資料存取都在 `holdings/store.py`，換資料庫只要寫一個有 `load()`、`previous()`、`save()` 三個方法的類別。網頁端呼叫的是 Supabase 的 REST API（`site/assets.js` 的雲端模式），換掉時要一起改。
