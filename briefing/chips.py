"""台股籌碼：三大法人買賣超、融資融券餘額，資料來自臺灣證券交易所（免費、不用金鑰）。

證交所當天資料大約 15:00（法人）、21:30（融資融券）後才有，沒有的話往回找最近一個交易日。
抓不到時回傳 None，由呼叫端沿用上一份。
"""
from __future__ import annotations

import json
import logging
import urllib.request
from datetime import date, datetime, timedelta, timezone

log = logging.getLogger(__name__)
TW = timezone(timedelta(hours=8))

INST_URL = "https://www.twse.com.tw/rwd/zh/fund/BFI82U?type=day&dayDate={d}&response=json"
FUT_URL = "https://openapi.taifex.com.tw/v1/MarketDataOfMajorInstitutionalTradersDetailsOfFuturesContractsBytheDate"
MARGIN_URL = "https://www.twse.com.tw/rwd/zh/marginTrading/MI_MARGN?date={d}&selectType=MS&response=json"


def _get_json(url: str) -> dict:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 invest-assistant"})
    with urllib.request.urlopen(req, timeout=15) as r:  # noqa: S310 固定的證交所網址
        return json.loads(r.read().decode("utf-8"))


def _num(s) -> float:
    return float(str(s).replace(",", "").strip() or 0)


def _iso(d: str) -> str:
    d = d.replace("-", "").replace("/", "")
    return f"{d[:4]}-{d[4:6]}-{d[6:8]}"


def parse_institutional(data: dict) -> dict | None:
    """BFI82U：單位名稱、買進金額、賣出金額、買賣差額（元）。回傳各法人買賣超（億元）。"""
    if data.get("stat") != "OK" or not data.get("data"):
        return None
    foreign = trust = dealer = 0.0
    for row in data["data"]:
        name, net = str(row[0]), _num(row[3])
        if name.startswith("外資"):
            foreign += net
        elif name.startswith("投信"):
            trust += net
        elif name.startswith("自營商"):
            dealer += net
    e8 = 1e8
    return {
        "date": _iso(data.get("date", "")),
        "foreign": round(foreign / e8, 2),
        "trust": round(trust / e8, 2),
        "dealer": round(dealer / e8, 2),
        "total": round((foreign + trust + dealer) / e8, 2),
    }


def _margin_rows(data: dict) -> list[list]:
    rows: list[list] = []
    for t in data.get("tables") or []:
        rows += t.get("data") or []
    rows += data.get("creditList") or []  # 舊版格式
    return rows


def parse_margin(data: dict) -> dict | None:
    """MI_MARGN 信用交易統計：項目、買進、賣出、現金(券)償還、前日餘額、今日餘額。"""
    if data.get("stat") != "OK":
        return None
    rows = {str(r[0]).strip(): r for r in _margin_rows(data) if r}
    amt = next((r for k, r in rows.items() if k.startswith("融資金額")), None)
    if amt is None:
        return None
    fin_lots = next((r for k, r in rows.items() if k.startswith("融資(交易單位)")), None)
    short_lots = next((r for k, r in rows.items() if k.startswith("融券(交易單位)")), None)
    today, prev = _num(amt[-1]), _num(amt[-2])  # 仟元
    out = {
        "date": _iso(data.get("date", "")),
        "margin_balance": round(today / 1e5, 1),          # 億元
        "margin_change": round((today - prev) / 1e5, 1),  # 億元
    }
    if short_lots is not None:
        out["short_lots"] = int(_num(short_lots[-1]))
        out["short_change"] = int(_num(short_lots[-1]) - _num(short_lots[-2]))
        if fin_lots is not None and _num(fin_lots[-1]):
            out["short_ratio"] = round(_num(short_lots[-1]) / _num(fin_lots[-1]) * 100, 2)  # 券資比 %
    return out


def parse_futures(rows: list[dict]) -> dict | None:
    """期交所 OpenAPI：三大法人期貨未平倉（最近一個交易日）。取臺股期貨的外資及陸資淨未平倉口數。"""
    for r in rows or []:
        if str(r.get("ContractCode", "")).strip() == "臺股期貨" and str(r.get("Item", "")).startswith("外資"):
            return {"date": _iso(str(r.get("Date", ""))), "foreign_oi": int(_num(r.get("OpenInterest(Net)")))}
    return None


def _latest(url: str, parse, today: date, lookback: int) -> dict | None:
    for i in range(lookback):
        d = today - timedelta(days=i)
        if d.weekday() >= 5:
            continue
        try:
            got = parse(_get_json(url.format(d=d.strftime("%Y%m%d"))))
        except Exception as e:  # noqa: BLE001
            log.warning("證交所 %s 抓取失敗：%s", d, e)
            continue
        if got:
            if not got["date"].strip("-"):
                got["date"] = d.isoformat()
            return got
    return None


def streak(history: list[dict], key: str) -> int:
    """最近連續幾天買超（正數）或賣超（負數）。history 由舊到新。"""
    n, sign = 0, 0
    for h in reversed(history):
        v = h.get(key) or 0
        s = 1 if v > 0 else -1 if v < 0 else 0
        if s == 0 or (sign and s != sign):
            break
        sign, n = s, n + 1
    return n * sign


def _who(v: float) -> str:
    return f"買超 {abs(v):,.1f} 億" if v > 0 else f"賣超 {abs(v):,.1f} 億" if v < 0 else "持平"


def _lots(v: int) -> str:
    return f"{abs(v) / 10000:.2f} 萬口" if abs(v) >= 10000 else f"{abs(v):,} 口"


def futures_note(fut: dict | None) -> str:
    if not fut:
        return ""
    v = fut["foreign_oi"]
    side = "淨多單" if v > 0 else "淨空單" if v < 0 else "多空持平"
    text = f"外資台指期{side} {_lots(v)}" if v else "外資台指期多空持平"
    ch = fut.get("change")
    if ch:
        # 數字變大＝偏多（空單減少或多單增加）
        text += f"，比前一天{'偏多' if ch > 0 else '偏空'} {_lots(ch)}"
    return text


def chips_notes(inst: dict | None, margin: dict | None, history: list[dict], fut: dict | None = None) -> list[str]:
    notes = []
    if inst:
        s = streak(history, "foreign")
        run = f"，連 {abs(s)} 天{'買' if s > 0 else '賣'}超" if abs(s) >= 2 else ""
        notes.append(f"外資{_who(inst['foreign'])}{run}；投信{_who(inst['trust'])}")
    if margin:
        ch = margin["margin_change"]
        move = f"增加 {ch:,.1f} 億" if ch > 0 else f"減少 {abs(ch):,.1f} 億" if ch < 0 else "持平"
        hint = "，散戶加碼" if ch >= 30 else "，散戶退場" if ch <= -30 else ""
        notes.append(f"融資餘額 {margin['margin_balance']:,.0f} 億，比前一天{move}{hint}")
    if fut:
        notes.append(futures_note(fut))
    return notes


def build_chips(cfg, previous: dict | None = None, today: date | None = None) -> dict | None:
    today = today or datetime.now(TW).date()
    previous = previous or {}
    inst = _latest(INST_URL, parse_institutional, today, cfg.CHIPS_LOOKBACK_DAYS)
    margin = _latest(MARGIN_URL, parse_margin, today, cfg.CHIPS_LOOKBACK_DAYS)
    try:
        fut = parse_futures(_get_json(FUT_URL))
    except Exception as e:  # noqa: BLE001
        log.warning("期交所未平倉抓取失敗：%s", e)
        fut = None
    if inst is None and margin is None and fut is None:
        return None
    inst = inst or previous.get("institutional")
    margin = margin or previous.get("margin")

    # 外資台指期未平倉：期交所只給最近一天，前一天的數字自己記
    fut_hist = [h for h in previous.get("futures_history", []) if not fut or h["date"] != fut["date"]]
    if fut:
        fut_hist.append({"date": fut["date"], "foreign_oi": fut["foreign_oi"]})
    fut_hist = sorted(fut_hist, key=lambda h: h["date"])[-cfg.CHIPS_HISTORY_DAYS:]
    fut = fut or previous.get("futures")
    if fut and len(fut_hist) >= 2 and fut_hist[-1]["date"] == fut["date"]:
        fut = {**fut, "change": fut_hist[-1]["foreign_oi"] - fut_hist[-2]["foreign_oi"]}

    history = [h for h in previous.get("history", []) if not inst or h.get("date") != inst["date"]]
    if inst:
        history.append({k: inst[k] for k in ("date", "foreign", "trust", "dealer")})
    history = sorted(history, key=lambda h: h["date"])[-cfg.CHIPS_HISTORY_DAYS:]
    return {
        "institutional": inst,
        "margin": margin,
        "history": history,
        "futures": fut,
        "futures_history": fut_hist,
        "foreign_streak": streak(history, "foreign"),
        "notes": chips_notes(inst, margin, history, fut),
    }
