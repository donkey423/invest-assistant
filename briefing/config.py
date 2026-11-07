"""早報要追蹤的指數、股票與新聞來源。要增減項目只改這個檔。"""

# 台股加權指數（主卡片）
TAIEX = {"symbol": "^TWII", "name": "台股加權指數"}

# 全球主要股市（9 格小走勢圖）
GLOBAL_INDICES = [
    {"symbol": "^GSPC", "name": "S&P 500"},
    {"symbol": "^IXIC", "name": "那斯達克"},
    {"symbol": "^N225", "name": "日經 225"},
    {"symbol": "^KS11", "name": "韓國 KOSPI"},
    {"symbol": "^HSI", "name": "香港恒生"},
    {"symbol": "000001.SS", "name": "上證"},
    {"symbol": "^GDAXI", "name": "德國 DAX"},
    {"symbol": "^FTSE", "name": "英國富時"},
    {"symbol": "^NSEI", "name": "印度 Nifty"},
]

# 美國 AI 股觀察清單
AI_STOCKS = [
    {"symbol": "NVDA", "name": "NVIDIA"},
    {"symbol": "MSFT", "name": "微軟"},
    {"symbol": "GOOGL", "name": "Google"},
    {"symbol": "META", "name": "Meta"},
    {"symbol": "AMZN", "name": "Amazon"},
    {"symbol": "AMD", "name": "AMD"},
    {"symbol": "AVGO", "name": "博通"},
    {"symbol": "TSM", "name": "台積電 ADR"},
]

# AI 股與這個指數比較
AI_BENCHMARK = {"symbol": "^IXIC", "name": "那斯達克"}

# 財經新聞 RSS。抓不到的來源會被略過，不影響其他來源。
NEWS_FEEDS = [
    {"name": "Google 新聞 財經", "url": "https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=zh-TW&gl=TW&ceid=TW:zh-Hant"},
    {"name": "Google 新聞 台股", "url": "https://news.google.com/rss/search?q=%E5%8F%B0%E8%82%A1&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"},
    {"name": "Google 新聞 美股", "url": "https://news.google.com/rss/search?q=%E7%BE%8E%E8%82%A1&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"},
    {"name": "Google 新聞 Fed", "url": "https://news.google.com/rss/search?q=Fed+%E5%88%A9%E7%8E%87&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"},
    {"name": "鉅亨網 台股", "url": "https://news.cnyes.com/rss/cat/tw_stock"},
    {"name": "中央社 財經", "url": "https://feeds.feedburner.com/rsscna/finance"},
]

# 每個來源最多取幾則、總共最多送幾則給 Claude
NEWS_PER_FEED = 25
NEWS_MAX_TOTAL = 120

# 走勢圖：主卡片畫一年，小圖畫最近 60 個交易日
TAIEX_CHART_DAYS = 250
SPARKLINE_DAYS = 60
