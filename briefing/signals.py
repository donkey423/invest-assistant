"""產業鏈訊號：上游訊號（手動）＋台股月營收（證交所／櫃買中心）＋代表股股價，算出每條鏈的燈號。

數字一律由程式計算。月營收每月 10 日前公布，openapi 只給最新一個月，
所以每次都把當月併進歷史（存在 latest.json），之後才看得出「由負轉正」「創新高」。
抓不到時沿用上一份，不影響早報其他區塊。
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from .chips import _get_json
from .market import _history, compute_quote

log = logging.getLogger(__name__)

REVENUE_URLS = [
    "https://openapi.twse.com.tw/v1/opendata/t187ap05_L",        # 上市
    "https://www.tpex.org.tw/openapi/v1/mopsfin_t187ap05_O",     # 上櫃
]
INPUTS_FILE = "chain_inputs.json"
HISTORY_MONTHS = 15
TREND_SCORE = {"up": 1, "flat": 0, "down": -1}
TREND_WORD = {"up": "轉強", "flat": "持平", "down": "轉弱"}
BENCH_NAMES = {"^SOX": "費城半導體", "^TWII": "台股加權指數", "^IXIC": "那斯達克"}


def _field(row: dict, *words: str):
    """證交所欄位名稱偶爾會改，用關鍵字找欄位。"""
    for k, v in row.items():
        if all(w in k for w in words):
            return v
    return None


def _f(v) -> float | None:
    try:
        return round(float(str(v).replace(",", "").strip()), 2)
    except (TypeError, ValueError):
        return None


def _ym(v) -> str | None:
    """'11410' 或 '202610' → '2026-10'。"""
    s = str(v or "").strip().replace("/", "")
    if not s.isdigit() or len(s) < 4:
        return None
    y, m = int(s[:-2]), int(s[-2:])
    if y < 1911:
        y += 1911
    return f"{y:04d}-{m:02d}" if 1 <= m <= 12 else None


def parse_revenue(rows: list[dict]) -> dict[str, dict]:
    """openapi 月營收彙總表 → {代號: {ym, name, rev, yoy, mom, ytd_yoy}}。營收單位：千元。"""
    out = {}
    for r in rows or []:
        code = str(_field(r, "公司代號") or "").strip()
        ym = _ym(_field(r, "資料年月"))
        rev = _f(_field(r, "當月營收"))
        if not code or not ym or rev is None:
            continue
        out[code] = {
            "ym": ym,
            "name": str(_field(r, "公司名稱") or "").strip(),
            "rev": rev,
            "yoy": _f(_field(r, "去年同月增減")),
            "mom": _f(_field(r, "上月比較增減")),
            "ytd_yoy": _f(_field(r, "前期比較增減")),
        }
    return out


def fetch_revenue(get_json=None) -> dict[str, dict]:
    get_json = get_json or _get_json
    out: dict[str, dict] = {}
    for url in REVENUE_URLS:
        try:
            out.update(parse_revenue(get_json(url)))
        except Exception as e:  # noqa: BLE001 一邊失敗另一邊照用
            log.warning("月營收抓取失敗 %s：%s", url, e)
    return out


def merge_history(prev: dict, latest: dict[str, dict], codes: set[str]) -> dict[str, list[dict]]:
    """每檔保留最近 HISTORY_MONTHS 個月 [{ym, rev, yoy}]，舊到新。"""
    hist = {c: list(v) for c, v in (prev or {}).items() if c in codes}
    for c in codes:
        r = latest.get(c)
        if not r:
            continue
        rows = [x for x in hist.get(c, []) if x["ym"] != r["ym"]]
        rows.append({"ym": r["ym"], "rev": r["rev"], "yoy": r["yoy"]})
        hist[c] = sorted(rows, key=lambda x: x["ym"])[-HISTORY_MONTHS:]
    return hist


def revenue_events(code: str, name: str, rev: dict, hist: list[dict], accel_pp: float) -> list[dict]:
    """這個月的營收有沒有值得通知的變化。"""
    ev = []
    ym, yoy, ytd = rev["ym"], rev.get("yoy"), rev.get("ytd_yoy")
    before = [h for h in hist if h["ym"] < ym]
    prev = before[-1] if before else None
    label = f"{name}（{code}）{ym[:4]} 年 {int(ym[5:])} 月營收"

    def add(kind, text):
        ev.append({"key": f"rev:{code}:{ym}:{kind}", "code": code, "name": name, "ym": ym, "kind": kind, "text": text})

    if yoy is not None and prev and prev.get("yoy") is not None:
        if prev["yoy"] < 0 <= yoy:
            add("turn_up", f"📈 {label}年增率由負轉正：{prev['yoy']:+.1f}% → {yoy:+.1f}%")
        elif prev["yoy"] >= 0 > yoy:
            add("turn_down", f"📉 {label}年增率由正轉負：{prev['yoy']:+.1f}% → {yoy:+.1f}%")
    if yoy is not None and ytd is not None:
        if yoy - ytd >= accel_pp:
            add("accel", f"🚀 {label}年增 {yoy:+.1f}%，比今年累計 {ytd:+.1f}% 明顯加速")
        elif yoy - ytd <= -accel_pp:
            add("decel", f"⚠️ {label}年增 {yoy:+.1f}%，比今年累計 {ytd:+.1f}% 明顯放緩")
    if len(before) >= 11 and rev["rev"] > max(h["rev"] for h in before):
        add("new_high", f"🏔 {label}創 {len(before) + 1} 個月新高（{rev['rev'] / 1e5:,.1f} 億元）")
    return ev


def _code(symbol: str) -> str | None:
    base, _, suffix = symbol.partition(".")
    return base if suffix in ("TW", "TWO") else None


def _avg(vals):
    vals = [v for v in vals if v is not None]
    return round(sum(vals) / len(vals), 2) if vals else None


def _median(vals):
    """用中位數，避免一檔營收暴增（例如年增 500%）把整條鏈拉偏。"""
    vals = sorted(v for v in vals if v is not None)
    if not vals:
        return None
    n = len(vals)
    return round(vals[n // 2] if n % 2 else (vals[n // 2 - 1] + vals[n // 2]) / 2, 2)


def market_input(item: dict, q: dict | None, pct: float) -> dict:
    """Yahoo 抓得到的上游價格（原油、銅、鋼、穀物、利率）→ 自動判斷轉強／轉弱。"""
    base = {"name": item["name"], "auto": True, "url": f"https://finance.yahoo.com/quote/{item['symbol']}"}
    if not q or q.get("chg_1m") is None:
        return {**base, "trend": None, "value": "抓不到價格", "as_of": ""}
    chg = q["chg_1m"]
    move = "up" if chg >= pct else "down" if chg <= -pct else "flat"
    if item.get("inverse") and move != "flat":
        move = "down" if move == "up" else "up"
    note = "（價格上漲對這條鏈不利）" if item.get("inverse") else ""
    return {**base, "trend": move, "value": f"近一個月 {chg:+.1f}%，現在 {q['last']:,}{note}", "as_of": q["as_of"]}


def chain_light(upstream: list[dict], accel: float | None, cfg) -> tuple[str, list[str]]:
    score, why = 0, []
    for u in upstream:
        t = u.get("trend")
        if t in TREND_SCORE:
            score += TREND_SCORE[t]
            why.append(f"{u['name']}{TREND_WORD[t]}")
    if accel is not None:
        if accel >= cfg.CHAIN_ACCEL_PP:
            score += 1
            why.append(f"月營收加速（單月年增比今年累計高 {accel:.1f} 個百分點，中位數）")
        elif accel <= -cfg.CHAIN_ACCEL_PP:
            score -= 1
            why.append(f"月營收放緩（單月年增比今年累計低 {-accel:.1f} 個百分點，中位數）")
        else:
            why.append("月營收成長速度持平")
    if not why:
        return "資料不足", ["上游訊號與月營收都還沒有資料"]
    return ("轉強" if score >= 1 else "轉弱" if score <= -1 else "持平"), why


def build_signals(cfg, market: dict, prev: dict | None, data_dir: Path,
                  history_fn=None, revenue_fn=None) -> dict:
    prev = prev or {}
    history_fn = history_fn or _history   # 執行時才取，測試可以換掉
    revenue_fn = revenue_fn or fetch_revenue
    chains_cfg = getattr(cfg, "CHAINS", [])
    try:
        inputs = json.loads((data_dir / INPUTS_FILE).read_text("utf-8"))
    except (OSError, ValueError):
        inputs = {}

    symbols = [s["symbol"] for c in chains_cfg for s in c["stocks"]]
    benches = {c.get("bench", "^TWII") for c in chains_cfg}
    benches |= {m["symbol"] for c in chains_cfg for m in c.get("market", [])}
    try:
        hist = history_fn(list(dict.fromkeys(symbols + sorted(benches)))) if symbols else {}
    except Exception as e:  # noqa: BLE001
        log.error("產業鏈股價抓取失敗：%s", e)
        hist = {}

    def quote(sym):
        if sym not in hist:
            return None
        try:
            return compute_quote(*hist[sym], spark_days=22)
        except ValueError:
            return None

    tw_codes = {c for c in (_code(s) for s in symbols) if c} | set(getattr(cfg, "REVENUE_WATCH", []))
    latest_rev = revenue_fn()
    prev_latest = prev.get("revenue_latest") or {}
    if not latest_rev:
        log.warning("這次沒有抓到月營收，沿用上一份")
    rev_now = {c: latest_rev.get(c) or prev_latest.get(c) for c in tw_codes}
    rev_now = {c: r for c, r in rev_now.items() if r}
    history = merge_history(prev.get("revenue_history") or {}, rev_now, tw_codes)

    events = []
    accel_pp = getattr(cfg, "REVENUE_ACCEL_PP", 10)
    for c, r in sorted(rev_now.items()):
        events += revenue_events(c, r.get("name") or c, r, history.get(c, []), accel_pp)

    chains = []
    for c in chains_cfg:
        stocks = []
        for s in c["stocks"]:
            q = quote(s["symbol"]) or {}
            code = _code(s["symbol"])
            r = rev_now.get(code) if code else None
            stocks.append({
                **s, "market": "台股" if code else ("韓股" if s["symbol"].endswith(".KS") else "美股"),
                **({k: q[k] for k in ("as_of", "last", "change_pct", "chg_1m", "range_pos", "spark")} if q else {"error": "抓不到資料"}),
                **({"rev_ym": r["ym"], "rev_yoy": r.get("yoy"), "rev_ytd_yoy": r.get("ytd_yoy")} if r else {}),
            })
        tw_rev = [s for s in stocks if s.get("rev_yoy") is not None]
        accels = [s["rev_yoy"] - s["rev_ytd_yoy"] for s in tw_rev if s.get("rev_ytd_yoy") is not None]
        accel = _median(accels)
        pct = getattr(cfg, "MARKET_TREND_PCT", 5)
        upstream = [market_input(m, quote(m["symbol"]), pct) for m in c.get("market", [])]
        upstream += inputs.get(c["id"]) or []
        light, why = chain_light(upstream, accel, cfg)
        bench = c.get("bench", "^TWII")
        bq = quote(bench)
        avg_1m = _avg([s.get("chg_1m") for s in stocks])
        bench_1m = bq["chg_1m"] if bq else None
        gap = round(avg_1m - bench_1m, 2) if avg_1m is not None and bench_1m is not None else None
        if gap is None:
            price_note = "股價資料不足"
        elif gap >= cfg.PRICED_IN_PP:
            price_note = f"代表股近一個月平均比對照指數多漲 {gap:.1f}%，好消息可能已經反映在股價"
        elif light == "轉強" and gap <= 0:
            price_note = "訊號轉強，但股價近一個月沒有跑贏對照指數，值得追蹤"
        else:
            price_note = f"代表股近一個月平均{'多' if gap >= 0 else '少'}漲對照指數 {abs(gap):.1f}%"
        chains.append({
            "id": c["id"], "name": c["name"], "group": c.get("group", ""), "desc": c.get("desc", ""),
            "light": light, "why": why, "upstream": upstream,
            "revenue": {"month": max((s["rev_ym"] for s in tw_rev), default=None),
                        "avg_yoy": _median([s["rev_yoy"] for s in tw_rev]), "avg_accel": accel,
                        "positive": sum(1 for s in tw_rev if s["rev_yoy"] > 0), "count": len(tw_rev)},
            "price": {"avg_1m": avg_1m, "bench": bench,
                      "bench_name": BENCH_NAMES.get(bench, bench), "bench_1m": bench_1m, "gap": gap, "note": price_note,
                      "bench_last": bq["last"] if bq else None},
            "stocks": stocks,
        })

    return {
        "chains": chains,
        "revenue_events": events,
        "revenue_latest": rev_now,
        "revenue_history": history,
    }
