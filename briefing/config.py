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

# 新聞 RSS。topic：finance 財經、world 國際局勢、ai AI 動態。抓不到的來源會被略過。
_GN = "https://news.google.com/rss/search?hl=zh-TW&gl=TW&ceid=TW:zh-Hant&q="
NEWS_FEEDS = [
    {"name": "Google 新聞 財經", "topic": "finance", "url": "https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=zh-TW&gl=TW&ceid=TW:zh-Hant"},
    {"name": "Google 新聞 台股", "topic": "finance", "url": _GN + "%E5%8F%B0%E8%82%A1"},
    {"name": "Google 新聞 美股", "topic": "finance", "url": _GN + "%E7%BE%8E%E8%82%A1"},
    {"name": "Google 新聞 Fed", "topic": "finance", "url": _GN + "Fed+%E5%88%A9%E7%8E%87"},
    {"name": "鉅亨網 台股", "topic": "finance", "url": "https://news.cnyes.com/rss/cat/tw_stock"},
    {"name": "中央社 財經", "topic": "finance", "url": "https://feeds.feedburner.com/rsscna/finance"},
    {"name": "Google 新聞 國際", "topic": "world", "url": "https://news.google.com/rss/headlines/section/topic/WORLD?hl=zh-TW&gl=TW&ceid=TW:zh-Hant"},
    {"name": "Google 新聞 地緣政治", "topic": "world", "url": _GN + "%E5%9C%B0%E7%B7%A3%E6%94%BF%E6%B2%BB+OR+%E9%97%9C%E7%A8%85+OR+%E5%88%B6%E8%A3%81"},
    {"name": "中央社 國際", "topic": "world", "url": "https://feeds.feedburner.com/rsscna/intworld"},
    {"name": "Google 新聞 AI", "topic": "ai", "url": _GN + "%E4%BA%BA%E5%B7%A5%E6%99%BA%E6%85%A7+OR+%E7%94%9F%E6%88%90%E5%BC%8FAI"},
    {"name": "Google 新聞 AI 產業", "topic": "ai", "url": _GN + "OpenAI+OR+%E8%BC%9D%E9%81%94+OR+AI%E6%99%B6%E7%89%87"},
    {"name": "中央社 科技", "topic": "ai", "url": "https://feeds.feedburner.com/rsscna/technology"},
]

# 每個來源最多取幾則、總共最多留幾則（財經、國際、AI 會各自保留一份）
NEWS_PER_FEED = 25
NEWS_MAX_TOTAL = 200

# 「今天的世界」地圖：每個地區的位置（經緯度）、標籤位置（亞洲擠在一起，所以拉開），
# 以及新聞標題出現哪些字就算這個地區。
REGIONS = [
    {"id": "us", "name": "美國", "lon": -98, "lat": 39,
     "words": ["美國", "美股", "Fed", "聯準會", "華爾街", "川普", "道瓊", "那指", "那斯達克", "費半", "白宮", "民主黨", "共和黨", "美債", "非農"]},
    {"id": "latam", "name": "拉丁美洲", "lon": -58, "lat": -15,
     "words": ["巴西", "阿根廷", "墨西哥", "巴拉圭", "智利", "委內瑞拉", "拉美", "哥倫比亞"]},
    {"id": "eu", "name": "歐洲", "lon": 6, "lat": 48,
     "words": ["歐洲", "歐股", "歐盟", "歐元", "德國", "英國", "法國", "義大利", "歐洲央行", "英國央行", "捷克", "荷蘭"]},
    {"id": "ru", "name": "俄烏", "lon": 38, "lat": 54,
     "words": ["俄羅斯", "俄國", "烏克蘭", "普丁", "澤倫斯基", "克里姆林", "基輔", "莫斯科"]},
    {"id": "me", "name": "中東", "lon": 46, "lat": 28,
     "words": ["中東", "以色列", "伊朗", "沙烏地", "加薩", "哈瑪斯", "真主黨", "葉門", "OPEC", "油價", "荷莫茲", "敘利亞", "黎巴嫩"]},
    {"id": "in", "name": "印度", "lon": 78, "lat": 22,
     "words": ["印度", "莫迪", "孟買"]},
    {"id": "cn", "name": "中國", "lon": 103, "lat": 34,
     "words": ["中國", "陸股", "上證", "北京", "人民幣", "習近平", "大陸", "中共", "港股", "香港", "恒生", "恆生", "解放軍"]},
    {"id": "sea", "name": "東南亞", "lon": 104, "lat": 8,
     "words": ["東南亞", "越南", "泰國", "印尼", "新加坡", "馬來西亞", "菲律賓", "東協"]},
    {"id": "kr", "name": "韓國", "lon": 127.5, "lat": 37, "label_lon": 121, "label_lat": 52,
     "words": ["韓國", "南韓", "韓股", "KOSPI", "三星", "SK海力士", "首爾", "北韓"]},
    {"id": "jp", "name": "日本", "lon": 139, "lat": 36, "label_lon": 157, "label_lat": 46,
     "words": ["日本", "日股", "日經", "日圓", "日幣", "日銀", "東京", "石破", "高市"]},
    {"id": "tw", "name": "台灣", "lon": 121, "lat": 23.7, "label_lon": 146, "label_lat": 17,
     "words": ["台股", "台灣", "臺灣", "台積電", "加權指數", "新台幣", "台幣", "金管會", "國安基金", "賴清德", "櫃買"]},
]

# 標題出現這些字，地圖上那個地區會加上「留意」標記
RISK_WORDS = ["戰爭", "衝突", "空襲", "飛彈", "攻擊", "制裁", "關稅", "封鎖", "軍演", "政變", "暴動", "停火", "入侵", "恐攻"]

# AI 世界動態：標題含這些字才算 AI 新聞，並依字詞分類
AI_WORDS = ["AI", "人工智慧", "生成式", "OpenAI", "ChatGPT", "Anthropic", "Claude", "Gemini", "輝達", "NVIDIA",
            "大模型", "語言模型", "算力", "資料中心", "機器人", "DeepSeek", "Grok", "Copilot", "晶片", "黃仁勳", "奧特曼"]
AI_CATEGORIES = [
    ("晶片", ["晶片", "半導體", "輝達", "NVIDIA", "GPU", "HBM", "台積電", "AMD", "博通", "黃仁勳", "算力", "DRAM", "資料中心"]),
    ("模型", ["OpenAI", "ChatGPT", "Anthropic", "Claude", "Gemini", "模型", "DeepSeek", "Grok", "Llama", "奧特曼", "Copilot"]),
    ("政策", ["監管", "法案", "禁令", "管制", "出口", "政策", "立法", "議員", "國會", "政府", "訴訟"]),
]

# 走勢圖：主卡片畫一年，小圖畫最近 60 個交易日
TAIEX_CHART_DAYS = 250
SPARKLINE_DAYS = 60
