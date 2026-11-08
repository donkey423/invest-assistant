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

# 市場溫度計：用 Yahoo 抓，跟股價同一套。kind 決定網頁上的白話解讀怎麼寫（見 gauges.py）
GAUGES = [
    {"symbol": "^VIX", "name": "VIX 恐慌指數", "kind": "vix"},
    {"symbol": "^TNX", "name": "美國 10 年債殖利率", "kind": "yield"},
    {"symbol": "DX-Y.NYB", "name": "美元指數", "kind": "dxy"},
    {"symbol": "TWD=X", "name": "美元兌台幣", "kind": "twd"},
    {"symbol": "^SOX", "name": "費城半導體", "kind": "sox"},
    {"symbol": "GC=F", "name": "黃金", "kind": "gold"},
    {"symbol": "CL=F", "name": "原油 WTI", "kind": "oil"},
    {"symbol": "BTC-USD", "name": "比特幣", "kind": "btc"},
]

# 台股籌碼（證交所）：往回找幾天有資料、保留幾天歷史來算「連幾天買超」
CHIPS_LOOKBACK_DAYS = 7
CHIPS_HISTORY_DAYS = 20

# 產業鏈訊號：每條鏈的代表股。股價用 Yahoo（上市 .TW、上櫃 .TWO），台股代號同時用來對證交所／櫃買中心的月營收。
# market：用 Yahoo 自動抓的上游價格（近一個月漲跌 ≥5% 算轉強／轉弱；inverse=True 代表這個價格漲對這條鏈是壞事，例如油價之於航空）。
# 其他上游訊號（報價、出口、運價、資本支出）放在 site/data/chain_inputs.json，手動更新。
# bench：拿來比較「股價已反映多少」的指數，不填 = 台股加權指數。
_S, _T = "^SOX", "^TWII"


def _st(*pairs):
    return [{"symbol": s, "name": n} for s, n in pairs]


CHAINS = [
    {"id": "memory", "name": "記憶體", "group": "半導體", "bench": _S,
     "desc": "AI 伺服器要大量 DRAM、HBM 與企業級 SSD；報價、韓國出口先動，台廠月營收接著反映。",
     "stocks": _st(("2408.TW", "南亞科"), ("2344.TW", "華邦電"), ("2337.TW", "旺宏"), ("3260.TWO", "威剛"),
                   ("8299.TWO", "群聯"), ("MU", "美光"), ("SNDK", "SanDisk"), ("000660.KS", "SK 海力士"))},
    {"id": "foundry", "name": "晶圓代工", "group": "半導體", "bench": _S,
     "desc": "先進製程看 AI 晶片與手機，成熟製程看消費電子與車用；台積電月營收是整個半導體的溫度計。",
     "stocks": _st(("2330.TW", "台積電"), ("2303.TW", "聯電"), ("5347.TWO", "世界"), ("6770.TW", "力積電"),
                   ("GFS", "格羅方德"), ("INTC", "英特爾"))},
    {"id": "ic_design", "name": "IC 設計", "group": "半導體", "bench": _S,
     "desc": "手機、PC、網通晶片與 AI ASIC；終端需求與庫存調整先反映在月營收。",
     "stocks": _st(("2454.TW", "聯發科"), ("3034.TW", "聯詠"), ("2379.TW", "瑞昱"), ("3443.TW", "創意"),
                   ("3661.TW", "世芯-KY"), ("QCOM", "高通"), ("AMD", "AMD"), ("AVGO", "博通"))},
    {"id": "semi_equip", "name": "半導體設備與先進封裝", "group": "半導體", "bench": _S,
     "desc": "晶圓廠與封測廠擴產 → 設備訂單；日本設備 B/B 比與台積電資本支出是領先訊號。",
     "stocks": _st(("3711.TW", "日月光投控"), ("3131.TWO", "弘塑"), ("6187.TWO", "萬潤"), ("3583.TW", "辛耘"),
                   ("2467.TW", "志聖"), ("AMAT", "應用材料"), ("LRCX", "科林研發"), ("8035.T", "東京威力"))},
    {"id": "wafer", "name": "矽晶圓", "group": "半導體", "bench": _S,
     "desc": "晶圓廠稼動率回升 → 矽晶圓長約與現貨價；景氣循環比晶圓代工晚一點。",
     "stocks": _st(("6488.TWO", "環球晶"), ("5483.TWO", "中美晶"), ("3532.TW", "台勝科"))},
    {"id": "ai_server", "name": "AI 伺服器", "group": "AI 與資料中心", "bench": _S,
     "desc": "雲端大廠資本支出 → GPU／ASIC → 伺服器組裝；台廠月營收比美國財報早 1～2 個月。",
     "stocks": _st(("2382.TW", "廣達"), ("6669.TW", "緯穎"), ("2317.TW", "鴻海"), ("3231.TW", "緯創"),
                   ("2356.TW", "英業達"), ("NVDA", "NVIDIA"), ("SMCI", "美超微"), ("DELL", "戴爾"))},
    {"id": "cooling", "name": "散熱", "group": "AI 與資料中心",
     "desc": "AI 晶片功耗越高越需要液冷；伺服器出貨與新平台規格決定散熱需求。",
     "stocks": _st(("3017.TW", "奇鋐"), ("3324.TWO", "雙鴻"), ("2421.TW", "建準"), ("3653.TW", "健策"),
                   ("VRT", "Vertiv"))},
    {"id": "power", "name": "電源", "group": "AI 與資料中心",
     "desc": "資料中心電源、UPS、高壓直流；跟著 AI 機櫃出貨與電力建設走。",
     "stocks": _st(("2308.TW", "台達電"), ("2301.TW", "光寶科"), ("6412.TW", "群電"), ("ETN", "伊頓"),
                   ("VRT", "Vertiv"))},
    {"id": "network", "name": "網通與光通訊", "group": "AI 與資料中心",
     "desc": "AI 叢集需要高速交換器與光模組（800G／1.6T、CPO）；交換器與光元件廠營收先動。",
     "stocks": _st(("2345.TW", "智邦"), ("4979.TWO", "華星光"), ("3081.TWO", "聯亞"), ("3363.TWO", "上詮"),
                   ("6442.TW", "光聖"), ("ANET", "Arista"), ("COHR", "Coherent"), ("LITE", "Lumentum"))},
    {"id": "pcb", "name": "PCB 與載板", "group": "電子零組件",
     "desc": "AI 伺服器用高層數板與 ABF 載板；銅箔基板（CCL）廠月營收常最早反映。",
     "stocks": _st(("2383.TW", "台光電"), ("2368.TW", "金像電"), ("3037.TW", "欣興"), ("8046.TW", "南電"),
                   ("3189.TW", "景碩"), ("2313.TW", "華通"), ("TTMI", "TTM"))},
    {"id": "passive", "name": "被動元件", "group": "電子零組件",
     "desc": "MLCC、電阻；景氣循環明顯，通路庫存與報價調漲是領先訊號。",
     "stocks": _st(("2327.TW", "國巨"), ("2492.TW", "華新科"), ("3026.TW", "禾伸堂"), ("2456.TW", "奇力新"),
                   ("VSH", "Vishay"))},
    {"id": "panel", "name": "面板", "group": "電子零組件",
     "desc": "電視、筆電面板報價每月兩次公布；報價止跌回升通常領先面板股。",
     "stocks": _st(("2409.TW", "友達"), ("3481.TW", "群創"), ("6116.TW", "彩晶"), ("LPL", "LG Display"))},
    {"id": "apple", "name": "手機與蘋果供應鏈", "group": "消費電子",
     "desc": "新機備貨期（約 6～9 月）拉貨，鏡頭、機殼、組裝廠月營收先反映。",
     "stocks": _st(("2317.TW", "鴻海"), ("3008.TW", "大立光"), ("4938.TW", "和碩"), ("2474.TW", "可成"),
                   ("AAPL", "蘋果"))},
    {"id": "pc", "name": "PC 與筆電", "group": "消費電子",
     "desc": "換機潮與 AI PC；品牌與代工廠月營收、Windows 更新週期是訊號。",
     "stocks": _st(("2357.TW", "華碩"), ("2353.TW", "宏碁"), ("2324.TW", "仁寶"), ("2377.TW", "微星"),
                   ("HPQ", "惠普"), ("DELL", "戴爾"))},
    {"id": "ev", "name": "電動車與車用", "group": "車用與能源",
     "desc": "電動車銷量與車用晶片庫存；特斯拉交車數、各國補貼政策是領先訊號。",
     "stocks": _st(("1536.TW", "和大"), ("2231.TW", "為升"), ("1533.TW", "車王電"), ("3665.TW", "貿聯-KY"),
                   ("2308.TW", "台達電"), ("TSLA", "特斯拉"))},
    {"id": "grid", "name": "重電與電網", "group": "車用與能源",
     "desc": "台電強韌電網計畫、資料中心用電、美國電網更新；變壓器訂單能見度很長。",
     "stocks": _st(("1519.TW", "華城"), ("1513.TW", "中興電"), ("1503.TW", "士電"), ("1514.TW", "亞力"),
                   ("GEV", "GE Vernova"), ("ETN", "伊頓"))},
    {"id": "solar", "name": "太陽能與儲能", "group": "車用與能源",
     "desc": "政策與電價驅動；矽料、模組報價與各國裝機量是訊號。",
     "stocks": _st(("3576.TW", "聯合再生"), ("6443.TW", "元晶"), ("6806.TW", "森崴能源"), ("FSLR", "First Solar"),
                   ("ENPH", "Enphase"))},
    {"id": "container", "name": "貨櫃航運", "group": "傳產與原物料",
     "desc": "SCFI 運價每週五公布，運價領先貨櫃三雄獲利；地緣政治（紅海、關稅）影響很大。",
     "stocks": _st(("2603.TW", "長榮"), ("2609.TW", "陽明"), ("2615.TW", "萬海"), ("ZIM", "以星"))},
    {"id": "bulk", "name": "散裝航運", "group": "傳產與原物料",
     "desc": "BDI 波羅的海指數反映鐵礦砂、煤、穀物運輸需求；跟中國基建與鋼鐵生產連動。",
     "stocks": _st(("2606.TW", "裕民"), ("2637.TW", "慧洋-KY"), ("2605.TW", "新興"), ("GNK", "Genco"))},
    {"id": "airline", "name": "航空", "group": "傳產與原物料",
     "desc": "客運量與油價；油價下跌對航空是好事。",
     "market": [{"symbol": "CL=F", "name": "原油 WTI", "inverse": True}],
     "stocks": _st(("2618.TW", "長榮航"), ("2610.TW", "華航"), ("2646.TW", "星宇航空"), ("DAL", "達美航空"))},
    {"id": "steel", "name": "鋼鐵", "group": "傳產與原物料",
     "desc": "中鋼每月開盤價、熱軋鋼捲價格與中國鋼市；基建與房市決定需求。",
     "market": [{"symbol": "HRC=F", "name": "美國熱軋鋼捲期貨"}],
     "stocks": _st(("2002.TW", "中鋼"), ("2014.TW", "中鴻"), ("2027.TW", "大成鋼"), ("2031.TW", "新光鋼"),
                   ("NUE", "Nucor"), ("STLD", "Steel Dynamics"))},
    {"id": "petchem", "name": "塑化", "group": "傳產與原物料",
     "desc": "原油成本與產品報價的價差；中國新產能是長期壓力。",
     "market": [{"symbol": "CL=F", "name": "原油 WTI"}],
     "stocks": _st(("1301.TW", "台塑"), ("1303.TW", "南亞"), ("1326.TW", "台化"), ("6505.TW", "台塑化"),
                   ("DOW", "陶氏"), ("LYB", "利安德巴塞爾"))},
    {"id": "copper", "name": "電線電纜（銅）", "group": "傳產與原物料",
     "desc": "銅價上漲時庫存利益與報價調漲；電網、資料中心建設帶動需求。",
     "market": [{"symbol": "HG=F", "name": "銅期貨"}],
     "stocks": _st(("1605.TW", "華新"), ("1609.TW", "大亞"), ("1608.TW", "華榮"), ("FCX", "自由港"))},
    {"id": "cement", "name": "水泥與營建", "group": "傳產與原物料",
     "desc": "營建與公共工程需求；煤價是成本。",
     "stocks": _st(("1101.TW", "台泥"), ("1102.TW", "亞泥"), ("2542.TW", "興富發"), ("VMC", "Vulcan"))},
    {"id": "food", "name": "食品與民生", "group": "傳產與原物料",
     "desc": "黃豆、玉米、小麥是成本；穀物價格下跌對食品廠毛利有利。",
     "market": [{"symbol": "ZC=F", "name": "玉米期貨", "inverse": True},
                {"symbol": "ZS=F", "name": "黃豆期貨", "inverse": True}],
     "stocks": _st(("1216.TW", "統一"), ("2912.TW", "統一超"), ("1201.TW", "味全"), ("1210.TW", "大成"))},
    {"id": "textile", "name": "紡織與製鞋", "group": "傳產與原物料",
     "desc": "歐美品牌庫存與訂單；Nike 等品牌財報與美國零售銷售是領先訊號。",
     "stocks": _st(("9910.TW", "豐泰"), ("9904.TW", "寶成"), ("1476.TW", "儒鴻"), ("1477.TW", "聚陽"),
                   ("NKE", "Nike"))},
    {"id": "automation", "name": "機器人與自動化", "group": "其他",
     "desc": "工廠自動化與人形機器人；工具機訂單、日本工具機協會數據是訊號。",
     "stocks": _st(("2049.TW", "上銀"), ("1590.TW", "亞德客-KY"), ("4583.TW", "台灣精銳"), ("ISRG", "直覺手術"),
                   ("TER", "泰瑞達"))},
    {"id": "defense", "name": "國防與無人機", "group": "其他",
     "desc": "各國國防預算與無人機採購；政策新聞是主要訊號。",
     "stocks": _st(("2634.TW", "漢翔"), ("8033.TW", "雷虎"), ("LMT", "洛克希德馬丁"), ("RTX", "RTX"))},
    {"id": "biotech", "name": "生技醫療", "group": "其他",
     "desc": "新藥審查進度、授權案與健保政策；個別公司差異大，產業訊號弱。",
     "stocks": _st(("6446.TW", "藥華藥"), ("6472.TW", "保瑞"), ("1760.TW", "寶齡富錦"), ("4743.TWO", "合一"),
                   ("LLY", "禮來"))},
    {"id": "finance", "name": "金融", "group": "其他",
     "desc": "利率上升有利銀行利差，壽險看債券與匯率；美債殖利率是主要訊號。",
     "market": [{"symbol": "^TNX", "name": "美國 10 年債殖利率"}],
     "stocks": _st(("2881.TW", "富邦金"), ("2882.TW", "國泰金"), ("2891.TW", "中信金"), ("2886.TW", "兆豐金"),
                   ("JPM", "摩根大通"))},
]
# 上游價格近一個月漲跌超過這個百分比算轉強／轉弱
MARKET_TREND_PCT = 5

# 月營收提醒額外追蹤的台股（產業鏈裡的台股都會自動加入）。只填代號。
REVENUE_WATCH = ["2330"]
# 年增率比今年累計年增率高（低）這麼多個百分點，就算「加速」（「放緩」）
REVENUE_ACCEL_PP = 10
# 鏈的燈號：台股成員平均「單月年增率 − 累計年增率」超過這個百分點算轉強／轉弱
CHAIN_ACCEL_PP = 3
# 鏈的代表股近一個月平均漲幅比對照指數多這麼多，就提醒「可能已反映」
PRICED_IN_PP = 10
