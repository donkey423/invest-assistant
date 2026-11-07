"""持股分析的設定。要改上限或情境只改這個檔。"""
from pathlib import Path

# 個人資料放在 private/（已列入 .gitignore，不會上傳）
HOLDINGS_CSV = Path("private/holdings.csv")
TRANSACTIONS_CSV = Path("private/transactions.csv")  # 選填：賣出與股息紀錄
# 輸出也放在不公開的資料夾，GitHub Pages 上看不到
OUT_DIR = Path("site/data/private")
# 早報的輸出，用來讓 Claude 對照今天的新聞
BRIEFING_JSON = Path("site/data/latest.json")

BASE_CURRENCY = "TWD"
FX_SYMBOLS = {"USD": "USDTWD=X"}  # 外幣對台幣匯率

# 超過就標紅
POSITION_LIMIT = 0.20  # 單一持股占總資產
SECTOR_LIMIT = 0.40    # 單一產業占總資產

# 與大盤比較、算 beta 用
BENCHMARKS = [
    {"symbol": "^TWII", "name": "台股加權指數"},
    {"symbol": "^GSPC", "name": "S&P 500"},
]
BETA_BENCHMARK = "^TWII"

# 情境試算：指數或匯率變動時，資產大約變多少（用各持股對該指數的 beta 估算）
SCENARIOS = [
    {"name": "費城半導體跌 10%", "symbol": "^SOX", "move": -0.10},
    {"name": "台股加權指數跌 10%", "symbol": "^TWII", "move": -0.10},
    {"name": "S&P 500 跌 10%", "symbol": "^GSPC", "move": -0.10},
    {"name": "美元兌台幣貶 3%", "fx": "USD", "move": -0.03},
]

# 持有未滿這麼多天不算年化報酬（太短的年化數字會誤導）
MIN_DAYS_FOR_ANNUALIZED = 90
