"""未來一週行事曆：Fed 利率決策、美國重要數據、財報／法說會、除權息。全部免費來源。

- 美國與主要央行數據：Forex Factory 公開的本週行事曆 JSON（只有「本週」，週末會少下週的）
- Fed 利率決策：config.FOMC_DATES 固定日期（每年 Fed 公布一次，記得每年補）
- 財報／法說會：yfinance 的 calendar（美股 AI 股＋台股權值股）
- 除權息：證交所除權除息預告表 TWT48U

任何一個來源失敗都略過，不影響其他。時間一律換成台灣時間。
"""
from __future__ import annotations

import json
import logging
import re
import urllib.request
from datetime import date, datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo

log = logging.getLogger(__name__)
TW = timezone(timedelta(hours=8))
NY = ZoneInfo("America/New_York")

FF_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
DIV_URL = "https://www.twse.com.tw/rwd/zh/exRight/TWT48U?response=json"

# Forex Factory 英文標題 → 中文。同一個中文名稱同一天只顯示一次（例如 CPI 月增、年增合併）
MACRO_NAMES = [
    ("Federal Funds Rate", "Fed 利率決策"),
    ("FOMC Statement", "Fed 利率決策"),
    ("FOMC Press Conference", "Fed 利率決策"),
    ("FOMC Meeting Minutes", "Fed 會議紀錄"),
    ("Fed Chair", "Fed 主席談話"),
    ("Non-Farm Employment Change", "美國非農就業"),
    ("Unemployment Rate", "美國非農就業"),
    ("Average Hourly Earnings", "美國非農就業"),
    ("Core CPI", "美國 CPI"),
    ("CPI", "美國 CPI"),
    ("Core PPI", "美國 PPI"),
    ("PPI", "美國 PPI"),
    ("Core PCE", "美國 PCE 物價"),
    ("GDP", "美國 GDP"),
    ("Retail Sales", "美國零售銷售"),
    ("ISM Manufacturing", "美國 ISM 製造業"),
    ("ISM Services", "美國 ISM 服務業"),
    ("JOLTS", "美國 JOLTS 職缺"),
    ("Unemployment Claims", "美國初領失業金"),
    ("Consumer Sentiment", "密大消費者信心"),
    ("BOJ Policy Rate", "日銀利率決策"),
    ("Main Refinancing Rate", "歐洲央行利率決策"),
]
FF_COUNTRIES = {"USD", "JPY", "EUR", "CNY"}
COUNTRY_NAME = {"USD": "美國", "JPY": "日本", "EUR": "歐元區", "CNY": "中國"}


def _get_json(url: str) -> object:
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 invest-assistant"})
    with urllib.request.urlopen(req, timeout=20) as r:  # noqa: S310 固定網址
        return json.loads(r.read().decode("utf-8"))


def _ev(when: datetime | date, kind: str, title: str, note: str = "", has_time: bool = True) -> dict:
    if isinstance(when, datetime):
        tw = when.astimezone(TW)
        return {"date": tw.date().isoformat(), "time": tw.strftime("%H:%M") if has_time else "",
                "kind": kind, "title": title, "note": note}
    return {"date": when.isoformat(), "time": "", "kind": kind, "title": title, "note": note}


# ---------- 總經數據 ----------

def macro_name(title: str, country: str) -> str:
    for key, name in MACRO_NAMES:
        if key.lower() in title.lower():
            if country == "USD" or not name.startswith("美國"):
                return name
    return f"{COUNTRY_NAME.get(country, country)} {title}"


def parse_ff(rows: list[dict]) -> list[dict]:
    out, seen = [], set()
    for r in rows:
        if r.get("impact") != "High" or r.get("country") not in FF_COUNTRIES:
            continue
        try:
            when = datetime.fromisoformat(r["date"])
        except (KeyError, ValueError):
            continue
        name = macro_name(r.get("title", ""), r["country"])
        if r["country"] != "USD" and name.startswith(COUNTRY_NAME[r["country"]]):
            continue  # 其他國家只列央行利率決策
        kind = "fed" if "Fed" in name or "央行" in name or "日銀" in name else "macro"
        note = "｜".join(x for x in (
            f"預估 {r['forecast']}" if r.get("forecast") else "",
            f"前值 {r['previous']}" if r.get("previous") else "") if x)
        ev = _ev(when, kind, name, note)
        key = (ev["date"], name)
        if key in seen:
            continue
        seen.add(key)
        out.append(ev)
    return out


def fomc_events(dates: list[str]) -> list[dict]:
    """Fed 利率決策：美東時間 14:00 公布（台灣時間隔天凌晨）。"""
    out = []
    for d in dates:
        when = datetime.combine(date.fromisoformat(d), time(14, 0), tzinfo=NY)
        out.append(_ev(when, "fed", "Fed 利率決策", "美東 14:00 公布，台灣時間隔天凌晨"))
    return out


# ---------- 財報／法說會 ----------

def _earnings_dates(symbols: list[str]) -> dict[str, date]:
    import yfinance as yf  # 延後匯入，測試時不需要

    out = {}
    for sym in symbols:
        try:
            cal = yf.Ticker(sym).calendar or {}
            ds = cal.get("Earnings Date") or []
            if ds:
                out[sym] = ds[0] if isinstance(ds[0], date) else date.fromisoformat(str(ds[0])[:10])
        except Exception as e:  # noqa: BLE001
            log.warning("抓不到 %s 的財報日：%s", sym, e)
    return out


def earnings_events(watch: list[dict], dates: dict[str, date]) -> list[dict]:
    out = []
    for w in watch:
        d = dates.get(w["symbol"])
        if d is None:
            continue
        tw = w["symbol"].endswith((".TW", ".TWO"))
        title = f"{w['name']} {'法說會／財報' if tw else '財報'}"
        note = "日期依 Yahoo，以公司公告為準" if tw else "美股多在盤後公布，台灣時間隔天早上"
        out.append(_ev(d, "earnings", title, note))
    return out


# ---------- 除權息 ----------

def _roc_date(s: str) -> date | None:
    m = re.match(r"(\d+)年(\d+)月(\d+)日", s or "")
    if not m:
        return None
    y, mo, d = (int(x) for x in m.groups())
    return date(y + 1911, mo, d)


def _cash(s: str) -> float | None:
    try:
        v = float(str(s).replace(",", ""))
    except ValueError:
        return None
    return v if v > 0 else None


def parse_dividends(data: dict, start: date, end: date, watch: dict[str, str]) -> tuple[list[dict], int]:
    """回傳（關注名單內的除權息事件, 這段期間其他家數）。"""
    if data.get("stat") != "OK":
        return [], 0
    f = {name: i for i, name in enumerate(data.get("fields", []))}
    i_date, i_code, i_name = f.get("除權除息日期", 0), f.get("股票代號", 1), f.get("名稱", 2)
    i_kind, i_cash = f.get("除權息", 3), f.get("現金股利", 7)
    events, others = [], 0
    for row in data.get("data", []):
        d = _roc_date(row[i_date])
        if d is None or not (start <= d <= end):
            continue
        code = str(row[i_code]).strip()
        if code not in watch:
            others += 1
            continue
        cash = _cash(row[i_cash]) if i_cash < len(row) else None
        note = f"現金股利 {cash:g} 元" if cash else "配息金額待公告"
        events.append(_ev(d, "dividend", f"{row[i_name]}（{code}）除{row[i_kind]}", note))
    return events, others


# ---------- 組合 ----------

def build_calendar(cfg, today: date | None = None, get_json=None, earnings_fn=None) -> dict:
    get_json = get_json or _get_json
    earnings_fn = earnings_fn or _earnings_dates
    today = today or datetime.now(TW).date()
    end = today + timedelta(days=cfg.CALENDAR_DAYS)
    events: list[dict] = []
    sources_ok = []

    try:
        events += parse_ff(get_json(FF_URL))
        sources_ok.append("總經")
    except Exception as e:  # noqa: BLE001
        log.warning("經濟行事曆抓取失敗：%s", e)
    events += fomc_events(cfg.FOMC_DATES)

    watch = [*cfg.AI_STOCKS, *cfg.CALENDAR_TW_WATCH]
    try:
        events += earnings_events(watch, earnings_fn([w["symbol"] for w in watch]))
        sources_ok.append("財報")
    except Exception as e:  # noqa: BLE001
        log.warning("財報日抓取失敗：%s", e)

    others = 0
    try:
        div, others = parse_dividends(get_json(DIV_URL), today, end, cfg.CALENDAR_DIV_WATCH)
        events += div
        sources_ok.append("除權息")
    except Exception as e:  # noqa: BLE001
        log.warning("除權息預告抓取失敗：%s", e)

    # 只留今天起的一週；同一天同名稱只留一筆（Fed 固定日期與數據來源重複時）
    seen, keep = set(), []
    for ev in sorted(events, key=lambda e: (e["date"], e["time"] or "99:99", e["title"])):
        if not (today.isoformat() <= ev["date"] <= end.isoformat()):
            continue
        key = (ev["date"], ev["title"])
        if key in seen:
            continue
        seen.add(key)
        keep.append(ev)
    return {"start": today.isoformat(), "end": end.isoformat(), "events": keep,
            "dividend_others": others, "sources": sources_ok}
