# 用你的 Claude 帳號寫 AI 摘要（雲端排程的工作說明）

這份是給雲端排程裡的 Claude 看的步驟。每個交易日早上執行一次。

1. 讀 `site/data/latest.json`（行情數字）與 `site/data/news.json`（新聞清單）。
   若 `latest.json` 的 `generated_at` 不是今天（台灣時間），照樣寫，但在 `market_comment` 開頭註明資料時間。
2. 寫出 `site/data/ai_summary.json`，格式：

```json
{
  "written_at": "2026-11-09T07:50+08:00",
  "headline": "今天市場的一句話總結，60 字內",
  "market_comment": "台股與美股的 2 到 3 句說明",
  "world_headline": "全球局勢一句話，60 字內（看 topic 為 world 的新聞）",
  "ai_headline": "AI 世界動態一句話，60 字內（看 topic 為 ai 的新聞）",
  "points": [
    {
      "tag": "央行｜經濟數據｜企業｜產業｜地緣政治｜市場 其中一個",
      "title": "20 字內",
      "summary": "一句話說明對市場的意義，50 字內",
      "sources": [{"title": "新聞標題", "url": "新聞連結", "source": "來源名稱"}]
    }
  ]
}
```

3. 規則：
   - 繁體中文、台灣用語，簡潔中立，不給買賣建議。
   - 只根據這兩個檔案的內容寫，不要上網找資料，也不要自己補數字或事件。
   - 引用漲跌幅時照抄 `latest.json` 的數字。
   - `points` 3 到 6 則，以 topic 為 finance 的新聞為主，最重要的放前面；`sources` 必須照抄 `news.json` 裡的 title、url、source。
   - `written_at` 用現在的台灣時間。
4. 執行 `python -m briefing.ai_file check site/data`，有 ✗ 就修到全部通過。
5. 只提交 `site/data/ai_summary.json`，訊息用 `AI 摘要 YYYY-MM-DD`，推到 `main`。
   推上去後 GitHub Actions 會自動重新產生早報、寄 Email、更新網站。
