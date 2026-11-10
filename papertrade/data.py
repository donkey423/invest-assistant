"""模擬帳戶要用的資料：日線（Yahoo）、三大法人個股買賣超與本益比（證交所／櫃買中心）。

都是免費、不用金鑰的來源。抓不到的部分回傳空的，選股方法會自動跳過缺資料的股票。
"""
from __future__ import annotations

import json
import logging
import time
import urllib.request

log = logging.getLogger(__name__)

T86_URL = "https://www.twse.com.tw/rwd/zh/fund/T86?date={d}&selectType=ALLBUT0999&response=json"
TPEX_INST_URL = "https://www.tpex.org.tw/openapi/v1/tpex_3insti_daily_trading"
VALUE_URLS = [
    "https://openapi.twse.com.tw/v1/exchangeReport/BWIBBU_ALL",
    "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_peratio_analysis",
]


def get_json(url: str):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 invest-assistant"})
    with urllib.request.urlopen(req, timeout=20) as r:  # noqa: S310 固定的公開資料網址
        return json.loads(r.read().decode("utf-8"))


def _num(v) -> float | None:
    try:
        s = str(v).replace(",", "").strip()
        return float(s) if s not in ("", "-", "--", "N/A") else None
    except (TypeError, ValueError):
        return None


def _key(row: dict, *words: str, without: tuple = ()):
    for k, v in row.items():
        kl = k.lower()
        if all(w.lower() in kl for w in words) and not any(x.lower() in kl for x in without):
            return v
    return None


def history(symbols) -> dict[str, dict]:
    """{代號: {"dates", "open", "close", "volume"}}，約 15 個月日線，舊到新。"""
    import yfinance as yf  # 延後匯入，測試時不需要

    symbols = list(dict.fromkeys(symbols))
    df = yf.download(symbols, period="15mo", interval="1d", auto_adjust=False,
                     group_by="ticker", progress=False, threads=True)
    out = {}
    for sym in symbols:
        try:
            s = df[sym][["Open", "Close", "Volume"]].dropna()
            if len(s) < 2:
                raise ValueError("no data")
            out[sym] = {"dates": [d.strftime("%Y-%m-%d") for d in s.index],
                        "open": [round(float(v), 4) for v in s["Open"].values],
                        "close": [round(float(v), 4) for v in s["Close"].values],
                        "volume": [float(v) for v in s["Volume"].values]}
        except Exception as e:  # noqa: BLE001 單一代號失敗不影響整體
            log.warning("抓不到 %s 的日線：%s", sym, e)
    return out


def parse_t86(data: dict) -> dict[str, dict]:
    """證交所 T86：每檔外資（不含外資自營商）與投信買賣超股數。"""
    if not isinstance(data, dict) or data.get("stat") != "OK":
        return {}
    fields = data.get("fields") or []

    def col(*words):
        for i, f in enumerate(fields):
            if all(w in f for w in words):
                return i
        return None

    ic, ifo, it = col("證券代號"), col("外陸資買賣超股數", "不含"), col("投信買賣超股數")
    if ifo is None:
        ifo = col("外資", "買賣超股數")
    if None in (ic, ifo, it):
        return {}
    out = {}
    for r in data.get("data") or []:
        code = str(r[ic]).strip()
        f, t = _num(r[ifo]), _num(r[it])
        if code and f is not None and t is not None:
            out[code] = {"foreign": f, "trust": t}
    return out


def parse_tpex_inst(rows) -> tuple[str | None, dict[str, dict]]:
    """櫃買中心三大法人（openapi 只有最新一天）。回傳（日期, {代號: {foreign, trust}}）。"""
    out, day = {}, None
    for r in rows or []:
        code = str(_key(r, "SecuritiesCompanyCode") or _key(r, "代號") or "").strip()
        f = _num(_key(r, "Foreign", "Difference", without=("Dealer",)) or _key(r, "外資", "買賣超", without=("自營",)))
        t = _num(_key(r, "Trust", "Difference") or _key(r, "投信", "買賣超"))
        d = str(_key(r, "Date") or _key(r, "日期") or "").strip()
        if d and day is None:
            day = _roc_date(d)
        if code and f is not None and t is not None:
            out[code] = {"foreign": f, "trust": t}
    return day, out


def _roc_date(s: str) -> str | None:
    s = s.replace("/", "").replace("-", "")
    if not s.isdigit() or len(s) < 7:
        return None
    y = int(s[:-4])
    y = y + 1911 if y < 1911 else y
    return f"{y:04d}-{s[-4:-2]}-{s[-2:]}"


def fetch_chips(dates: list[str], cache: dict, get=get_json) -> dict[str, dict]:
    """取得指定交易日的個股法人買賣超（股數），已抓過的日期用快取。"""
    out = {d: cache[d] for d in dates if cache.get(d)}
    for d in dates:
        if d in out:
            continue
        try:
            rows = parse_t86(get(T86_URL.format(d=d.replace("-", ""))))
            if rows:
                out[d] = rows
            time.sleep(1.5)  # 證交所有流量限制
        except Exception as e:  # noqa: BLE001
            log.warning("證交所 T86 %s 抓取失敗：%s", d, e)
    try:
        day, rows = parse_tpex_inst(get(TPEX_INST_URL))
        if day in dates and rows:
            out[day] = {**rows, **out.get(day, {})}
    except Exception as e:  # noqa: BLE001 上櫃抓不到就只用上市
        log.warning("櫃買中心法人資料抓取失敗：%s", e)
    return out


def parse_value(rows) -> dict[str, dict]:
    """本益比、殖利率、股價淨值比（上市 BWIBBU_ALL／上櫃 peratio_analysis）。"""
    out = {}
    for r in rows or []:
        code = str(_key(r, "Code") or _key(r, "代號") or "").strip()
        pe = _num(_key(r, "PEratio") or _key(r, "PriceEarningRatio") or _key(r, "本益比"))
        dy = _num(_key(r, "DividendYield") or _key(r, "YieldRatio") or _key(r, "殖利率"))
        pb = _num(_key(r, "PBratio") or _key(r, "PriceBookRatio") or _key(r, "淨值比"))
        if code:
            out[code] = {"pe": pe, "yield": dy, "pb": pb}
    return out


def fetch_value(get=get_json) -> dict[str, dict]:
    out = {}
    for url in VALUE_URLS:
        try:
            out.update(parse_value(get(url)))
        except Exception as e:  # noqa: BLE001
            log.warning("本益比資料抓取失敗 %s：%s", url, e)
    return out
