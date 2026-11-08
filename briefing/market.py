"""抓行情並計算漲跌幅、一年區間位置與走勢圖資料。

數字一律在這裡由程式計算，不交給 AI。
"""
from __future__ import annotations

import logging
from typing import Iterable

from .gauges import gauge_note

log = logging.getLogger(__name__)


def _pct(now: float, before: float | None) -> float | None:
    if before is None or before == 0:
        return None
    return round((now / before - 1) * 100, 2)


def compute_quote(dates: list[str], closes: list[float], spark_days: int) -> dict:
    """由日期與收盤價序列（舊到新）算出卡片要的數字。"""
    if len(closes) < 2:
        raise ValueError("收盤價資料不足")
    last = closes[-1]

    def back(n: int) -> float | None:
        return closes[-1 - n] if len(closes) > n else closes[0]

    year = closes[-252:] if len(closes) >= 252 else closes
    hi, lo = max(year), min(year)
    return {
        "as_of": dates[-1],
        "last": round(last, 2),
        "change": round(last - closes[-2], 2),
        "change_pct": _pct(last, closes[-2]),
        "chg_5d": _pct(last, back(5)),
        "chg_1m": _pct(last, back(21)),
        "chg_1y": _pct(last, back(251)),
        "high_52w": round(hi, 2),
        "low_52w": round(lo, 2),
        # 0 = 一年最低，1 = 一年最高
        "range_pos": round((last - lo) / (hi - lo), 3) if hi > lo else 0.5,
        "spark": [round(c, 2) for c in closes[-spark_days:]],
    }


def _history(symbols: Iterable[str]) -> dict[str, tuple[list[str], list[float]]]:
    """用 yfinance 一次抓所有代號約 13 個月的日線。失敗的代號會被略過。"""
    import yfinance as yf  # 延後匯入，測試時不需要

    symbols = list(dict.fromkeys(symbols))
    df = yf.download(
        symbols, period="13mo", interval="1d", auto_adjust=False,
        group_by="ticker", progress=False, threads=True,
    )
    out: dict[str, tuple[list[str], list[float]]] = {}
    for sym in symbols:
        try:
            s = df[sym]["Close"].dropna()
            if len(s) < 2:
                raise ValueError("no data")
            out[sym] = ([d.strftime("%Y-%m-%d") for d in s.index], [float(v) for v in s.values])
        except Exception as e:  # noqa: BLE001 單一代號失敗不影響整體
            log.warning("抓不到 %s 的行情：%s", sym, e)
    return out


def build_market(cfg, history_fn=_history) -> dict:
    """回傳早報的行情區塊。history_fn 可替換成測試用的假資料。"""
    gauges_cfg = getattr(cfg, "GAUGES", [])
    items = [cfg.TAIEX, *cfg.GLOBAL_INDICES, *cfg.AI_STOCKS, cfg.AI_BENCHMARK, *gauges_cfg]
    hist = history_fn(i["symbol"] for i in items)

    def quote(item: dict, spark_days: int = cfg.SPARKLINE_DAYS) -> dict:
        sym = item["symbol"]
        if sym not in hist:
            return {**item, "error": "抓不到資料"}
        dates, closes = hist[sym]
        return {**item, **compute_quote(dates, closes, spark_days)}

    taiex = quote(cfg.TAIEX, cfg.TAIEX_CHART_DAYS)
    if "error" not in taiex:
        dates, _ = hist[cfg.TAIEX["symbol"]]
        taiex["spark_dates"] = dates[-cfg.TAIEX_CHART_DAYS:]

    return {
        "taiex": taiex,
        "global": [quote(i) for i in cfg.GLOBAL_INDICES],
        "ai_stocks": [quote(i) for i in cfg.AI_STOCKS],
        "ai_benchmark": quote(cfg.AI_BENCHMARK),
        "gauges": [{**q, "note": gauge_note(q)} for q in map(quote, gauges_cfg)],
    }
