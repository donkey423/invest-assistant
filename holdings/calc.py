"""持股的所有數字：市值、損益、配置、集中度、與大盤比較、情境試算。

數字一律由程式計算，Claude 只拿結果來解讀。
"""
from __future__ import annotations

import bisect
import math
from collections import defaultdict
from datetime import date

from .model import Position, Transaction

History = dict[str, tuple[list[str], list[float]]]  # 代號 → (日期, 收盤價)，舊到新


def _r(x: float | None, n: int = 2) -> float | None:
    return None if x is None else round(x, n)


def _pct(x: float | None) -> float | None:
    return None if x is None else round(x * 100, 2)


def price_on(hist: History, sym: str, day: str) -> float | None:
    """某天（或之前最近一個交易日）的收盤價。"""
    if sym not in hist:
        return None
    dates, closes = hist[sym]
    i = bisect.bisect_right(dates, day) - 1
    return closes[i] if i >= 0 else None


def _fx_now(hist: History, ccy: str, fx_symbols: dict) -> float | None:
    if ccy == "TWD":
        return 1.0
    sym = fx_symbols.get(ccy)
    return hist[sym][1][-1] if sym in hist else None


def value_positions(positions: list[Position], hist: History, cfg, today: date) -> tuple[list[dict], list[str]]:
    """每一筆持股的市值與損益（原幣與台幣）。抓不到行情的會標 error，不計入總額。"""
    rows, warnings = [], []
    for p in positions:
        row = {
            "symbol": p.symbol, "quote_symbol": p.quote_symbol, "name": p.name, "market": p.market,
            "currency": p.currency, "account": p.account, "sector": p.sector, "thesis": p.thesis,
            "shares": p.shares, "avg_cost": p.avg_cost,
            "buy_date": p.buy_date.isoformat() if p.buy_date else None,
        }
        fx = _fx_now(hist, p.currency, cfg.FX_SYMBOLS)
        if p.quote_symbol not in hist or fx is None:
            row["error"] = "抓不到行情" if p.quote_symbol not in hist else f"抓不到 {p.currency} 匯率"
            warnings.append(f"{p.symbol}：{row['error']}，這檔沒有算進總額")
            rows.append(row)
            continue

        dates, closes = hist[p.quote_symbol]
        price = closes[-1]
        cost_local = p.shares * p.avg_cost
        value_local = p.shares * price
        ret = value_local / cost_local - 1 if cost_local else None

        # 外幣部位：買入匯率優先用 CSV 填的，沒填就用買入日的歷史匯率
        fx_cost, fx_cost_source = 1.0, "TWD"
        if p.currency != "TWD":
            if p.fx_cost:
                fx_cost, fx_cost_source = p.fx_cost, "填寫"
            elif p.buy_date and (h := price_on(hist, cfg.FX_SYMBOLS[p.currency], p.buy_date.isoformat())):
                fx_cost, fx_cost_source = h, "歷史匯率"
            else:
                fx_cost, fx_cost_source = fx, "未知（用目前匯率，匯率影響算 0）"
        cost_twd = cost_local * fx_cost
        value_twd = value_local * fx
        pnl_twd = value_twd - cost_twd

        days = (today - p.buy_date).days if p.buy_date else None
        ret_twd = value_twd / cost_twd - 1 if cost_twd else None
        annual = None
        if days and days >= cfg.MIN_DAYS_FOR_ANNUALIZED and ret_twd is not None and ret_twd > -1:
            annual = (1 + ret_twd) ** (365 / days) - 1

        row.update({
            "price": _r(price), "price_date": dates[-1], "day_change_pct": _pct(price / closes[-2] - 1) if len(closes) > 1 else None,
            "value_local": _r(value_local), "cost_local": _r(cost_local),
            "pnl_local": _r(value_local - cost_local), "return_pct": _pct(ret),
            "fx": _r(fx, 4), "fx_cost": _r(fx_cost, 4), "fx_cost_source": fx_cost_source,
            "value_twd": round(value_twd), "cost_twd": round(cost_twd), "pnl_twd": round(pnl_twd),
            "return_twd_pct": _pct(ret_twd), "holding_days": days, "annualized_pct": _pct(annual),
        })
        if p.currency != "TWD":
            # 台幣損益拆成「股價漲跌」與「匯率變動」兩塊
            row["pnl_from_price_twd"] = round((value_local - cost_local) * fx_cost)
            row["pnl_from_fx_twd"] = round(value_local * (fx - fx_cost))
        rows.append(row)
    return rows, warnings


def _group(rows: list[dict], key: str, total: float, limit: float | None) -> list[dict]:
    agg = defaultdict(lambda: {"value_twd": 0, "cost_twd": 0, "count": 0})
    for r in rows:
        a = agg[r[key]]
        a["value_twd"] += r["value_twd"]
        a["cost_twd"] += r["cost_twd"]
        a["count"] += 1
    out = []
    for k, a in sorted(agg.items(), key=lambda kv: -kv[1]["value_twd"]):
        w = a["value_twd"] / total if total else 0
        out.append({"key": k, "value_twd": a["value_twd"], "weight_pct": _pct(w), "count": a["count"],
                    "pnl_twd": a["value_twd"] - a["cost_twd"],
                    "return_pct": _pct(a["value_twd"] / a["cost_twd"] - 1) if a["cost_twd"] else None,
                    "over_limit": bool(limit and w > limit)})
    return out


def allocation(rows: list[dict], cfg) -> dict:
    ok = [r for r in rows if "error" not in r]
    total = sum(r["value_twd"] for r in ok)
    # 同一檔在不同帳戶要合併算占比
    by_symbol = _group(ok, "symbol", total, cfg.POSITION_LIMIT)
    names = {r["symbol"]: r["name"] for r in ok}
    for g in by_symbol:
        g["name"] = names.get(g["key"], "")
    weights = [g["value_twd"] / total for g in by_symbol] if total else []
    hhi = sum(w * w for w in weights)
    return {
        "by_symbol": by_symbol,
        "by_market": _group(ok, "market", total, None),
        "by_currency": _group(ok, "currency", total, None),
        "by_sector": _group(ok, "sector", total, cfg.SECTOR_LIMIT),
        "by_account": _group(ok, "account", total, None),
        "concentration": {
            "top1_pct": _pct(weights[0]) if weights else None,
            "top3_pct": _pct(sum(weights[:3])) if weights else None,
            "hhi": round(hhi, 4),
            # 「等於幾檔平均分配」：10 檔平均就是 10，越小越集中
            "effective_n": round(1 / hhi, 1) if hhi else None,
            "position_limit_pct": _pct(cfg.POSITION_LIMIT), "sector_limit_pct": _pct(cfg.SECTOR_LIMIT),
            "over_limit": [g["key"] for g in by_symbol if g["over_limit"]],
            "sector_over_limit": [g["key"] for g in _group(ok, "sector", total, cfg.SECTOR_LIMIT) if g["over_limit"]],
        },
    }


def totals(rows: list[dict], realized: dict) -> dict:
    ok = [r for r in rows if "error" not in r]
    value = sum(r["value_twd"] for r in ok)
    cost = sum(r["cost_twd"] for r in ok)
    day_pnl = 0.0
    for r in ok:
        if r.get("day_change_pct") is not None:
            prev = r["value_twd"] / (1 + r["day_change_pct"] / 100)
            day_pnl += r["value_twd"] - prev
    fx_pnl = sum(r.get("pnl_from_fx_twd", 0) for r in ok)
    return {
        "value_twd": value, "cost_twd": cost, "unrealized_twd": value - cost,
        "unrealized_pct": _pct(value / cost - 1) if cost else None,
        "day_pnl_twd": round(day_pnl),
        "pnl_from_fx_twd": fx_pnl,
        "realized_twd": realized["realized_twd"], "dividends_twd": realized["dividends_twd"],
        "dividends_this_year_twd": realized["dividends_this_year_twd"],
        "total_pnl_twd": value - cost + realized["realized_twd"] + realized["dividends_twd"],
        "positions": len(ok), "missing": len(rows) - len(ok),
    }


def realized_pnl(txs: list[Transaction], hist: History, cfg, today: date) -> dict:
    """已實現損益與股息，以交易日的匯率換成台幣。"""
    realized = divs = divs_year = 0.0
    items = []
    for t in txs:
        fx = 1.0
        if t.currency != "TWD":
            fx = price_on(hist, cfg.FX_SYMBOLS.get(t.currency, ""), t.date.isoformat()) or _fx_now(hist, t.currency, cfg.FX_SYMBOLS) or 0
        if t.type == "sell":
            amt = (t.shares * (t.price - t.avg_cost) - t.fee) * fx
            realized += amt
        else:
            amt = (t.amount - t.fee) * fx
            divs += amt
            if t.date.year == today.year:
                divs_year += amt
        items.append({"date": t.date.isoformat(), "symbol": t.symbol, "type": t.type, "twd": round(amt)})
    return {"realized_twd": round(realized), "dividends_twd": round(divs),
            "dividends_this_year_twd": round(divs_year), "items": items}


# ---------- 與大盤比較、beta、最大回撤、情境試算 ----------

def _returns(series: list[float]) -> list[float]:
    return [b / a - 1 for a, b in zip(series, series[1:]) if a]


def _aligned(hist: History, symbols: list[str], days: int = 252) -> tuple[list[str], dict[str, list[float]]]:
    """把多個代號對到同一組日期（台美休市日不同，缺的用前一天價格補）。"""
    present = [s for s in symbols if s in hist]
    if not present:
        return [], {}
    all_dates = sorted({d for s in present for d in hist[s][0]})[-days:]
    out = {}
    for s in present:
        series, last = [], None
        for d in all_dates:
            last = price_on(hist, s, d) or last
            series.append(last)
        if None in series:  # 這檔資料起始日比較晚，往回補第一個有的價格
            first = next(v for v in series if v is not None)
            series = [first if v is None else v for v in series]
        out[s] = series
    return all_dates, out


def beta(xs: list[float], ys: list[float]) -> float | None:
    """ys 對 xs 的 beta（兩組日報酬）。"""
    n = min(len(xs), len(ys))
    if n < 20:
        return None
    xs, ys = xs[-n:], ys[-n:]
    mx, my = sum(xs) / n, sum(ys) / n
    var = sum((x - mx) ** 2 for x in xs)
    if var == 0:
        return None
    return sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / var


def max_drawdown(series: list[float]) -> float:
    peak, mdd = -math.inf, 0.0
    for v in series:
        peak = max(peak, v)
        mdd = min(mdd, v / peak - 1)
    return mdd


def risk(rows: list[dict], hist: History, cfg) -> dict:
    """以「目前持股不動」回推過去一年的走勢，和大盤比較。"""
    ok = [r for r in rows if "error" not in r]
    if not ok:
        return {}
    fx_syms = {r["currency"]: cfg.FX_SYMBOLS[r["currency"]] for r in ok if r["currency"] != "TWD"}
    scen_syms = [s["symbol"] for s in cfg.SCENARIOS if "symbol" in s]
    bench_syms = [b["symbol"] for b in cfg.BENCHMARKS]
    syms = list(dict.fromkeys([r["quote_symbol"] for r in ok] + list(fx_syms.values()) + bench_syms + scen_syms))
    dates, s = _aligned(hist, syms)
    if len(dates) < 2:
        return {}

    def fx_series(ccy):
        return s[fx_syms[ccy]] if ccy in fx_syms and fx_syms[ccy] in s else [1.0] * len(dates)

    port = [0.0] * len(dates)
    for r in ok:
        fxs = fx_series(r["currency"])
        for i, (p, f) in enumerate(zip(s[r["quote_symbol"]], fxs)):
            port[i] += r["shares"] * p * f
    port_ret = _returns(port)

    benches = []
    for b in cfg.BENCHMARKS:
        if b["symbol"] in s:
            ser = s[b["symbol"]]
            benches.append({**b, "return_pct": _pct(ser[-1] / ser[0] - 1), "max_drawdown_pct": _pct(max_drawdown(ser))})

    # 每檔對各情境指數的 beta（台幣計價報酬）
    def pos_ret(r):
        fxs = fx_series(r["currency"])
        return _returns([p * f for p, f in zip(s[r["quote_symbol"]], fxs)])

    per_pos = {r["quote_symbol"]: pos_ret(r) for r in ok}
    scenarios = []
    total = sum(r["value_twd"] for r in ok)
    for sc in cfg.SCENARIOS:
        if "fx" in sc:
            hit = sum(r["value_twd"] for r in ok if r["currency"] == sc["fx"]) * sc["move"]
            scenarios.append({"name": sc["name"], "est_change_twd": round(hit),
                              "est_change_pct": _pct(hit / total) if total else None, "method": "外幣部位直接乘匯率變動"})
            continue
        if sc["symbol"] not in s:
            scenarios.append({"name": sc["name"], "error": "抓不到指數資料"})
            continue
        idx = _returns(s[sc["symbol"]])
        hit, detail = 0.0, []
        for r in ok:
            b = beta(idx, per_pos[r["quote_symbol"]])
            if b is None:
                continue
            chg = r["value_twd"] * b * sc["move"]
            hit += chg
            detail.append({"symbol": r["symbol"], "beta": round(b, 2), "est_change_twd": round(chg)})
        detail.sort(key=lambda d: d["est_change_twd"])
        scenarios.append({"name": sc["name"], "est_change_twd": round(hit),
                          "est_change_pct": _pct(hit / total) if total else None,
                          "method": "依過去一年各持股對該指數的 beta 估算", "worst": detail[:3]})

    b_idx = _returns(s[cfg.BETA_BENCHMARK]) if cfg.BETA_BENCHMARK in s else []
    b = beta(b_idx, port_ret) if b_idx else None
    return {
        "from": dates[0], "to": dates[-1],
        "note": "以目前持股不動回推過去一年，不含期間買賣",
        "return_pct": _pct(port[-1] / port[0] - 1) if port[0] else None,
        "max_drawdown_pct": _pct(max_drawdown(port)),
        "volatility_pct": _pct(_stdev(port_ret) * math.sqrt(252)) if len(port_ret) > 1 else None,
        "beta": _r(b), "beta_vs": cfg.BETA_BENCHMARK,
        "benchmarks": benches,
        "scenarios": scenarios,
        "series": {"dates": dates, "value_twd": [round(v) for v in port]},
    }


def _stdev(xs: list[float]) -> float:
    m = sum(xs) / len(xs)
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (len(xs) - 1))
