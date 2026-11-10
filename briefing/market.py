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


def _daily(sym: str, period: str) -> tuple[list[str], list[float]] | None:
    import yfinance as yf

    s = yf.Ticker(sym).history(period=period, interval="1d", auto_adjust=False)["Close"].dropna()
    if len(s) < 1:
        return None
    return [d.strftime("%Y-%m-%d") for d in s.index], [float(v) for v in s.values]


def _hourly_as_daily(sym: str) -> tuple[list[str], list[float]] | None:
    """用最近 5 天的小時線，取每天最後一筆當收盤。

    Yahoo 的日線偶爾會少掉最新一兩天（2026-11-10 實測：美股個股日線停在 11/6，指數卻有 11/9；
    台股指數日線少了 11/9），小時線走另一組資料，通常是完整的。
    """
    import yfinance as yf

    s = yf.Ticker(sym).history(period="5d", interval="60m", auto_adjust=False)["Close"].dropna()
    if len(s) < 1:
        return None
    by_day: dict[str, float] = {}
    for ts, v in zip(s.index, s.values):
        if ts.weekday() >= 5:      # 期貨週日晚上開盤的那幾小時不算一個交易日
            continue
        by_day[ts.strftime("%Y-%m-%d")] = float(v)   # 交易所當地日期，後面的蓋掉前面的
    days = sorted(by_day)
    return days, [by_day[d] for d in days]


def merge_series(base: tuple[list[str], list[float]] | None,
                 extra: tuple[list[str], list[float]] | None,
                 fill_only: bool = False) -> tuple[list[str], list[float]] | None:
    """依日期合併兩組收盤價。同一天預設以 extra 為準；fill_only=True 時只補 base 沒有的日期。
    extra 比 base 第一天還早的日期不收（避免把短期資料接到長期資料前面）。"""
    if not extra or not extra[0]:
        return base
    if not base or not base[0]:
        return extra
    merged = dict(zip(*base))
    first = base[0][0]
    for day, close in zip(*extra):
        if day < first or (fill_only and day in merged):
            continue
        merged[day] = close
    days = sorted(merged)
    return days, [merged[d] for d in days]


def _history(symbols: Iterable[str], patch_all: bool = False) -> dict[str, tuple[list[str], list[float]]]:
    """用 yfinance 一次抓所有代號約 13 個月的日線，再把缺的最新幾天補上。失敗的代號會被略過。

    Yahoo 的日線偶爾會少掉最新一兩天，而且每個代號缺的不一樣。補法：
    - 批次抓不到的代號，單獨重抓日線；
    - 資料日比其他代號舊的（patch_all=True 時是全部），用小時線補上最近 5 天缺的日期。
    """
    import yfinance as yf  # 延後匯入，測試時不需要
    from concurrent.futures import ThreadPoolExecutor

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
        except Exception:  # noqa: BLE001 單一代號失敗不影響整體，下面會單獨重抓
            pass

    newest = max((v[0][-1] for v in out.values()), default="")
    todo = [s for s in symbols if patch_all or s not in out or out[s][0][-1] < newest]

    def fetch(sym):
        base = out.get(sym)
        try:
            if base is None:
                base = _daily(sym, "13mo")
            return sym, merge_series(base, _hourly_as_daily(sym), fill_only=True)
        except Exception as e:  # noqa: BLE001
            log.warning("補抓 %s 失敗：%s", sym, e)
            return sym, base

    patched = 0
    if todo:
        with ThreadPoolExecutor(max_workers=8) as pool:
            for sym, merged in pool.map(fetch, todo):
                if merged and len(merged[1]) >= 2:
                    patched += sym not in out or merged[0] != out[sym][0]
                    out[sym] = merged
        log.info("檢查 %d 檔的最新資料，補上缺漏 %d 檔", len(todo), patched)
    for sym in symbols:
        if sym not in out:
            log.warning("抓不到 %s 的行情", sym)
    return out


TWSE_TAIEX_URL = "https://www.twse.com.tw/rwd/zh/afterTrading/FMTQIK?date={d}&response=json"


def parse_fmtqik(data: dict) -> tuple[list[str], list[float]]:
    """證交所每日市場成交資訊：日期（民國）…發行量加權股價指數。"""
    if not isinstance(data, dict) or data.get("stat") != "OK":
        return [], []
    fields = data.get("fields") or []
    idx = next((i for i, f in enumerate(fields) if "加權股價指數" in f), 4)
    dates, closes = [], []
    for row in data.get("data") or []:
        try:
            y, m, d = str(row[0]).strip().split("/")
            dates.append(f"{int(y) + 1911:04d}-{int(m):02d}-{int(d):02d}")
            closes.append(float(str(row[idx]).replace(",", "")))
        except (ValueError, IndexError):
            continue
    return dates, closes


def twse_taiex() -> tuple[list[str], list[float]] | None:
    """證交所官方的加權指數收盤（這個月與上個月），Yahoo 落後時用來補。"""
    import json
    import urllib.request
    from datetime import datetime, timedelta, timezone

    today = datetime.now(timezone(timedelta(hours=8))).date()
    first = today.replace(day=1)
    out: tuple[list[str], list[float]] = ([], [])
    for day in (first - timedelta(days=1), today):
        req = urllib.request.Request(TWSE_TAIEX_URL.format(d=day.strftime("%Y%m%d")),
                                     headers={"User-Agent": "Mozilla/5.0 invest-assistant"})
        try:
            with urllib.request.urlopen(req, timeout=15) as r:  # noqa: S310 固定的證交所網址
                d, c = parse_fmtqik(json.loads(r.read().decode("utf-8")))
        except Exception as e:  # noqa: BLE001
            log.warning("證交所加權指數抓取失敗：%s", e)
            continue
        out = (out[0] + d, out[1] + c)
    return out if out[0] else None


def weekdays_behind(as_of: str | None, today: str) -> int:
    """資料日到今天之間隔了幾個平日（不含資料日當天）。"""
    from datetime import date, timedelta

    if not as_of:
        return 99
    a, t = date.fromisoformat(as_of), date.fromisoformat(today)
    n, d = 0, a + timedelta(days=1)
    while d <= t:
        n += d.weekday() < 5
        d += timedelta(days=1)
    return n


def mark_stale(q: dict, today: str) -> dict:
    """資料日落後 2 個平日以上（例如週二早上還是上週五的資料）就標記，網頁會提醒。"""
    if "as_of" in q and weekdays_behind(q["as_of"], today) >= 2:
        q["stale"] = True
    return q


def build_market(cfg, history_fn=None, taiex_fn=None, today: str | None = None) -> dict:
    """回傳早報的行情區塊。history_fn、taiex_fn 可替換成測試用的假資料。"""
    from datetime import datetime, timedelta, timezone

    today = today or datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")
    gauges_cfg = getattr(cfg, "GAUGES", [])
    items = [cfg.TAIEX, *cfg.GLOBAL_INDICES, *cfg.AI_STOCKS, cfg.AI_BENCHMARK, *gauges_cfg]
    # 首頁這幾十個指數與個股每次都用小時線檢查最近幾天有沒有缺
    hist = history_fn(i["symbol"] for i in items) if history_fn else _history((i["symbol"] for i in items), patch_all=True)

    # 台股加權指數以證交所官方收盤為準：Yahoo 少了最新幾天就補上
    tsym = cfg.TAIEX["symbol"]
    try:
        official = (taiex_fn or twse_taiex)()
    except Exception as e:  # noqa: BLE001
        log.warning("證交所加權指數失敗：%s", e)
        official = None
    if official:
        hist[tsym] = merge_series(hist.get(tsym), official)

    def quote(item: dict, spark_days: int = cfg.SPARKLINE_DAYS) -> dict:
        sym = item["symbol"]
        if sym not in hist:
            return {**item, "error": "抓不到資料"}
        dates, closes = hist[sym]
        try:
            return mark_stale({**item, **compute_quote(dates, closes, spark_days)}, today)
        except ValueError:
            return {**item, "error": "抓不到資料"}

    taiex = quote(cfg.TAIEX, cfg.TAIEX_CHART_DAYS)
    if "error" not in taiex:
        dates, _ = hist[tsym]
        taiex["spark_dates"] = dates[-cfg.TAIEX_CHART_DAYS:]

    return {
        "taiex": taiex,
        "global": [quote(i) for i in cfg.GLOBAL_INDICES],
        "ai_stocks": [quote(i) for i in cfg.AI_STOCKS],
        "ai_benchmark": quote(cfg.AI_BENCHMARK),
        "gauges": [{**q, "note": gauge_note(q)} for q in map(quote, gauges_cfg)],
    }


def keep_newer(market: dict, prev: dict | None, today: str | None = None) -> dict:
    """新資料不可以比上一份舊：某個代號這次的資料日比上次早，就沿用上次的數字。

    Yahoo 偶爾會回傳少了最新一天的資料（2026-11-10 早上台股從 11/9 退回 11/6），
    這是最後一道保護。
    """
    if not prev:
        return market
    from datetime import datetime, timedelta, timezone

    today = today or datetime.now(timezone(timedelta(hours=8))).strftime("%Y-%m-%d")

    def pick(new: dict, old: dict | None) -> dict:
        if not old or old.get("symbol") != new.get("symbol") or "as_of" not in old:
            return new
        if "error" in new or new.get("as_of", "") < old["as_of"]:
            log.warning("%s 這次的資料比上一份舊，沿用上一份（%s）", new.get("symbol"), old["as_of"])
            kept = {k: v for k, v in old.items() if k != "stale"}
            return mark_stale({**kept, "kept_previous": True}, today)
        return new

    out = dict(market)
    for key in ("taiex", "ai_benchmark"):
        if isinstance(market.get(key), dict):
            out[key] = pick(market[key], prev.get(key))
    for key in ("global", "ai_stocks", "gauges"):
        old = {q.get("symbol"): q for q in prev.get(key) or []}
        out[key] = [pick(q, old.get(q.get("symbol"))) for q in market.get(key) or []]
    return out
