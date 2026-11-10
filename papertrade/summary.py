"""把模擬帳戶的狀態整理成網頁要的 papertrade.json：各方法績效、和大盤比較、持股、交易、選股命中率。"""
from __future__ import annotations

from bisect import bisect_right

from . import config as C
from .engine import market_value, price_on

PICK_HORIZON = 5  # 選股命中率：看推薦後 5 個交易日


def _mdd(values: list[float]) -> float:
    peak, worst = None, 0.0
    for v in values:
        peak = v if peak is None or v > peak else peak
        worst = min(worst, v / peak - 1)
    return round(worst * 100, 2)


def bench_series(state: dict, px: dict) -> dict:
    out = {}
    for b in C.BENCHMARKS:
        s = px.get(b["symbol"])
        if not s or not state["start"]:
            continue
        o = price_on(s, state["start"], "open", exact=True) or price_on(s, state["start"])
        # 指數缺第一天時，用前一天收盤當起點
        if not o:
            continue
        out[b["symbol"]] = {"name": b["name"], "equity": [
            {"date": d, "equity": round(C.START_CASH * (price_on(s, d) or o) / o)} for d in state["days"]]}
    return out


def pick_hits(state: dict, px: dict, sym: dict, trade_dates: list[str]) -> dict:
    """每天各方法的前 5 名，推薦後（隔天開盤買）5 個交易日有沒有贏大盤。不管有沒有真的買。"""
    taiex, etf = px.get("^TWII"), px.get("0050.TW")
    res = {}
    for j in state["journal"]:
        i = bisect_right(trade_dates, j["date"])
        if i + PICK_HORIZON - 1 >= len(trade_dates):
            continue
        d0, d1 = trade_dates[i], trade_dates[i + PICK_HORIZON - 1]
        bo, bc = price_on(taiex, d0, "open", exact=True), price_on(taiex, d1, exact=True)
        if not bo or not bc:  # 指數缺資料時改用 0050
            bo, bc = price_on(etf, d0, "open", exact=True), price_on(etf, d1, exact=True)
        if not bo or not bc:
            continue
        br = bc / bo - 1
        r = res.setdefault(j["method"], {"n": 0, "hit": 0, "excess": 0.0})
        for p in j["picks"]:
            s = px.get(sym.get(p["code"]))
            o, c = price_on(s, d0, "open", exact=True), price_on(s, d1)
            if not o or not c:
                continue
            ex = c / o - 1 - br
            r["n"] += 1
            r["hit"] += ex > 0
            r["excess"] += ex
    return {k: {"n": v["n"], "hit_rate": round(v["hit"] / v["n"] * 100, 1) if v["n"] else None,
                "avg_excess": round(v["excess"] / v["n"] * 100, 2) if v["n"] else None} for k, v in res.items()}


def build(state: dict, px: dict, sym: dict, names: dict, trade_dates: list[str], ctx: dict, generated_at: str) -> dict:
    bench = bench_series(state, px)
    tw = (bench.get("^TWII") or {}).get("equity") or []
    tw_last = tw[-1]["equity"] if tw else None
    hits = pick_hits(state, px, sym, trade_dates)
    last_day = state["days"][-1] if state["days"] else state["last_decision"]
    methods = []
    for m in C.METHODS:
        acc = state["accounts"][m["id"]]
        eq = [e["equity"] for e in acc["equity"]]
        last = eq[-1] if eq else C.START_CASH
        ret = (last / C.START_CASH - 1) * 100
        beat = 0
        for k in range(len(acc["equity"])):
            prev_a = eq[k - 1] if k else C.START_CASH
            prev_b = tw[k - 1]["equity"] if k and k - 1 < len(tw) else C.START_CASH
            if k < len(tw) and eq[k] / prev_a > tw[k]["equity"] / prev_b:
                beat += 1
        sells = [t for t in acc["trades"] if t["side"] == "賣"]
        holdings = []
        for code, pos in acc["positions"].items():
            c = price_on(px.get(sym.get(code)), last_day) if last_day else None
            c = c or pos["price"]
            holdings.append({"code": code, "name": names.get(code, ""), "shares": pos["shares"], "price": pos["price"],
                             "last": round(c, 2), "value": round(pos["shares"] * c),
                             "pnl_pct": round((pos["shares"] * c / pos["cost"] - 1) * 100, 2),
                             "date": pos["date"], "reason": pos["reason"]})
        latest = next((j for j in reversed(state["journal"]) if j["method"] == m["id"]), None)
        methods.append({
            **{k: m[k] for k in ("id", "name", "how", "basis", "sources")},
            "equity_now": last, "return_pct": round(ret, 2),
            "excess_pct": round(ret - (tw_last / C.START_CASH - 1) * 100, 2) if tw_last else None,
            "mdd_pct": _mdd([C.START_CASH, *eq]), "beat_days": beat, "days": len(eq),
            "cash": round(acc["cash"]), "invested": round(market_value(acc, last_day, px, sym)) if last_day else 0,
            "fees": round(acc["fees"]), "trades": len(acc["trades"]),
            "win_rate": round(sum(t["pnl"] > 0 for t in sells) / len(sells) * 100, 1) if sells else None,
            "closed": len(sells), "picks_hit": hits.get(m["id"]),
            "equity": acc["equity"], "holdings": sorted(holdings, key=lambda h: -h["value"]),
            "recent_trades": acc["trades"][-30:][::-1],
            "latest": latest, "pending": acc.get("pending"),
        })
    mname = {m["id"]: m["name"] for m in C.METHODS}
    ranked = sorted(methods, key=lambda x: x["return_pct"], reverse=True)
    for i, m in enumerate(ranked):
        m["rank"] = i + 1
    return {
        "generated_at": generated_at, "status": state["status"], "start": state["start"], "end": state["end"],
        "days_done": len(state["days"]), "days_total": C.TRADING_DAYS, "last_decision": state["last_decision"],
        "start_cash": C.START_CASH, "top_n": C.TOP_N, "keep_rank": C.KEEP_RANK,
        "costs": {"fee_rate": C.FEE_RATE, "fee_min": C.FEE_MIN, "tax_rate": C.TAX_RATE},
        "universe_size": len(sym), "business_cycle": C.BUSINESS_CYCLE, "regime": ctx.get("regime"),
        "pick_horizon": PICK_HORIZON,
        "benchmarks": bench, "methods": methods,
        "journal": [j for j in state["journal"] if j["date"] >= (state["journal"][-1]["date"] if state["journal"] else "")],
        "history": _journal_days(state, names),
        "all_trades": sorted(({**t, "method": mid, "method_name": mname[mid]} for mid, a in state["accounts"].items()
                              if mid in mname for t in a["trades"]),
                             key=lambda t: (t["date"], t["side"] == "買"), reverse=True)[:400],
        "warnings": ctx.get("warnings", []),
    }


def _journal_days(state: dict, names: dict) -> list[dict]:
    """每個決策日各方法買進／賣出的摘要（新到舊）。"""
    days = {}
    nm = lambda c: f"{names.get(c, '')}{c}"  # noqa: E731
    for j in state["journal"]:
        days.setdefault(j["date"], []).append({"method": j["method"], "buys": [nm(c) for c in j["buys"]],
                                               "sells": [nm(s["code"]) for s in j["sells"]]})
    return [{"date": d, "items": v} for d, v in sorted(days.items(), reverse=True)]
