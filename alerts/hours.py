"""判斷現在哪個市場在交易，讓盤中排程只檢查開盤中的股票。

台股：週一到週五 09:00–13:30（台灣時間）
美股：週一到週五 09:30–16:00（紐約時間，夏令／冬令時間自動處理）
收盤後再多檢查 CLOSE_GRACE_MIN 分鐘，抓到收盤價的變化。國定假日不另外判斷：
休市時行情不會動，同一條件一天也只通知一次，所以只是多抓幾次資料。
"""
from __future__ import annotations

from datetime import datetime, time
from zoneinfo import ZoneInfo

TW_TZ = ZoneInfo("Asia/Taipei")
NY_TZ = ZoneInfo("America/New_York")
CLOSE_GRACE_MIN = 20

SESSIONS = {
    "tw": (TW_TZ, time(9, 0), time(13, 30)),
    "us": (NY_TZ, time(9, 30), time(16, 0)),
}


def market_of(symbol: str) -> str:
    s = symbol.upper()
    return "tw" if s.endswith((".TW", ".TWO")) or s in ("^TWII", "^TWOII") else "us"


def is_open(market: str, now: datetime, grace_min: int = CLOSE_GRACE_MIN) -> bool:
    tz, start, end = SESSIONS[market]
    local = now.astimezone(tz)
    if local.weekday() >= 5:
        return False
    minutes = local.hour * 60 + local.minute
    return start.hour * 60 + start.minute <= minutes <= end.hour * 60 + end.minute + grace_min


def open_markets(now: datetime) -> set[str]:
    return {m for m in SESSIONS if is_open(m, now)}
