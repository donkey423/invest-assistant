"""模擬帳戶的設定。要調整方法、檔數、手續費只改這個檔。"""

START_CASH = 1_000_000          # 每個方法各自的起始資金（新台幣）
TRADING_DAYS = 30               # 模擬幾個交易日
TOP_N = 5                       # 每個方法最多同時持有幾檔（等權重）
KEEP_RANK = 10                  # 持股掉出前幾名才賣（避免每天換股吃手續費）
FEE_RATE = 0.001425             # 券商手續費（買賣各一次，不打折）
FEE_MIN = 20                    # 每筆最低手續費
TAX_RATE = 0.003                # 證交稅（賣出）
BENCHMARKS = [{"symbol": "^TWII", "name": "台股加權指數"}, {"symbol": "0050.TW", "name": "元大台灣50"}]

# 每種方法的說明與依據。id 對應 methods.py 的函式。
METHODS = [
    {"id": "momentum", "name": "價格動能 12-1",
     "how": "過去 12 個月漲最多（扣掉最近 1 個月）的股票，續抱強勢股。",
     "basis": "國際最常見的動能因子（Jegadeesh & Titman）；但台灣學術研究發現台股動能效應偏弱，正好拿來驗證。",
     "sources": [{"title": "Momentum in machine learning: Evidence from the Taiwan stock market（Pacific-Basin Finance Journal, 2023）",
                  "url": "https://scholar.nycu.edu.tw/en/publications/momentum-in-machine-learning-evidence-from-the-taiwan-stock-marke/"},
                 {"title": "多因子選股：價值、動能、品質、低波動", "url": "https://ctyeh.com/stock/knowledge/12785"}]},
    {"id": "reversal", "name": "短期反轉",
     "how": "近 1 個月跌最多、但月營收仍年增的股票，賭超跌回彈。",
     "basis": "台股散戶比重高，短期過度反應後常見反轉；加上營收年增過濾，避開基本面轉壞的股票。",
     "sources": [{"title": "Momentum in machine learning: Evidence from the Taiwan stock market（台股是動能效應的少數例外）",
                  "url": "https://scholar.nycu.edu.tw/en/publications/momentum-in-machine-learning-evidence-from-the-taiwan-stock-marke/"}]},
    {"id": "revenue", "name": "月營收加速",
     "how": "最新單月營收年增率比今年累計年增率高最多的股票。",
     "basis": "台股月營收每月 10 日前公布，比季報早，營收加速常領先股價與財報。",
     "sources": [{"title": "公開資訊觀測站 月營收彙總（證交所 openapi）", "url": "https://openapi.twse.com.tw/"}]},
    {"id": "trust", "name": "投信買超",
     "how": "前一交易日投信買超金額最大的 5 檔，每檔固定抱 11 個交易日。",
     "basis": "政大 2025 碩士論文回測 2015–2025：投信買超前 5 名、持有 11 天，扣成本後仍贏 0050。",
     "sources": [{"title": "投信買賣超對短期股價報酬之預測能力（政治大學，2025）",
                  "url": "https://thesis.lib.nccu.edu.tw/thesis/detail/6dc0d826502151f91645c4d5148a2aa2"}],
     "hold_days": 11},
    {"id": "foreign", "name": "外資連續買超",
     "how": "近 5 個交易日外資累計買超金額最大、且股價在 20 日均線之上的股票。",
     "basis": "中央大學研究：外資在台股是動能交易者，對大型股的買賣能預測後續報酬。",
     "sources": [{"title": "Does foreign investors' trade predict stock return? Evidence from Taiwan（中央大學）",
                  "url": "https://scholars.ncu.edu.tw/en/publications/does-foreign-investors-trade-predict-stock-return-evidence-from-t/"}]},
    {"id": "value", "name": "低本益比＋高殖利率",
     "how": "殖利率 ≥ 3.5%、近 3 個月沒有下跌，再依本益比低、殖利率高、股價淨值比低綜合排名。",
     "basis": "價值因子長期年化約贏大盤 2–4%（文獻整理），加上近 3 個月走勢過濾避開價值陷阱。",
     "sources": [{"title": "多因子選股：價值、動能、品質、低波動", "url": "https://ctyeh.com/stock/knowledge/12785"}]},
    {"id": "chain", "name": "產業鏈領先訊號",
     "how": "燈號「轉強」的產業鏈裡，月營收年增最強的代表股（每條鏈最多 1 檔）。",
     "basis": "本網站的產業鏈訊號：上游報價、出口先動，月營收確認，股價最後反映。",
     "sources": [{"title": "產業鏈訊號頁", "url": "https://donkey423.github.io/invest-assistant/"}]},
    {"id": "ai_theme", "name": "AI 讀新聞推理",
     "how": "每天早上 AI 讀新聞寫的「主題推理」裡點名的台股（近 5 天出現過的才續抱）。",
     "basis": "用 Claude 每天讀財經新聞、法說與報價消息，推理出受惠的產業與公司。",
     "sources": [{"title": "今日早報 主題推理", "url": "https://donkey423.github.io/invest-assistant/"}]},
    {"id": "combo", "name": "綜合評分＋景氣",
     "how": "動能、營收、外資、價值、產業鏈五種分數平均後取前 5 名；景氣燈號與大盤趨勢決定持股比例。",
     "basis": "多因子平均能降低單一因子失靈的風險；景氣紅燈時台股未來一年報酬歷史上偏高，跌破季線且 VIX 偏高時降低持股。",
     "sources": [{"title": "景氣紅燈時台股未來一年報酬（科技新報）", "url": "https://finance.technews.tw/2024/08/16/red-light/"},
                 {"title": "國發會：9 月景氣燈號連十紅", "url": "https://finance.technews.tw/2026/10/29/september-business-climate-indicator-shows-10-consecutive-red-lights-setting-new-historical-record/"}]},
]

# 景氣對策信號（國發會每月底公布上個月）。手動更新：light 填 紅燈／黃紅燈／綠燈／黃藍燈／藍燈
BUSINESS_CYCLE = {"month": "2026-09", "light": "紅燈", "score": 41,
                  "url": "https://finance.technews.tw/2026/10/29/september-business-climate-indicator-shows-10-consecutive-red-lights-setting-new-historical-record/"}
