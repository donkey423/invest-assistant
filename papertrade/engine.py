"""模擬帳戶引擎：隔天開盤成交、每天收盤結算、記下每次選股的理由。

流程（每次執行，決策日 D＝最近一個已收盤的交易日）：
1. 把上次決策後、到 D 為止的每個交易日依序處理：先用「開盤價」成交上次的委託，再用收盤價結算。
2. 滿 TRADING_DAYS 個交易日就停止，不再下單。
3. 否則用到 D 收盤為止的資料選股，產生下一個交易日開盤要成交的委託。
同一天重跑會先還原到上次處理前的狀態，所以結果不會重複計算。
"""
from __future__ import annotations

import copy
import math
from bisect import bisect_right

from . import config as C
from .methods import METHOD_FNS, exposure

MIN_ORDER = 10_000


def price_on(series: dict | None, day: str, field: str = "close", exact: bool = False):
    """某天的價格；exact=False 時找不到就用之前最近一天的收盤價（停牌）。"""
    if not series:
        return None
    i = bisect_right(series["dates"], day) - 1
    if i < 0:
        return None
    if series["dates"][i] == day:
        return series[field][i]
    return None if exact else series["close"][i]


def new_state() -> dict:
    return {"version": 1, "start": None, "end": None, "status": "running", "days": [], "last_decision": None,
            "accounts": {m["id"]: new_account() for m in C.METHODS}, "journal": [], "chips_cache": {},
            "ai_hist": [], "checkpoint": None}


def new_account() -> dict:
    return {"cash": float(C.START_CASH), "positions": {}, "pending": None, "equity": [], "trades": [], "fees": 0.0}


def fee(amount: float) -> float:
    return max(C.FEE_MIN, amount * C.FEE_RATE) if amount > 0 else 0.0


def _fill(acc: dict, day: str, px: dict, sym: dict, names: dict):
    p = acc.get("pending")
    if not p or p["decided"] >= day:
        return
    for s in p["sells"]:
        pos = acc["positions"].get(s["code"])
        o = price_on(px.get(sym.get(s["code"])), day, "open", exact=True)
        if not pos or not o:
            continue
        n = min(s.get("shares") or pos["shares"], pos["shares"])   # 委託帶 shares＝部分賣出（假設 E1 的等比例減碼才會帶）
        part = n < pos["shares"]
        gross = n * o
        f, tax = fee(gross), gross * C.TAX_RATE
        net = gross - f - tax
        acc["cash"] += net
        acc["fees"] += f + tax
        cost = pos["cost"] * n / pos["shares"] if part else pos["cost"]   # 賣掉的那部分所占的成本
        pnl = net - cost
        acc["trades"].append({"date": day, "side": "賣", "code": s["code"], "name": names.get(s["code"], ""),
                              "shares": n, "price": round(o, 2), "fee": round(f + tax),
                              "pnl": round(pnl), "pnl_pct": round(pnl / cost * 100, 2), "reason": s["reason"],
                              "held_from": pos["date"], **({"partial": True} if part else {})})
        if part:   # 剩下的股數：成本與已領股利等比例縮小，每股成本、每股已領股利都不變
            keep = (pos["shares"] - n) / pos["shares"]
            pos["cost"] = round(pos["cost"] - cost, 2)
            if "div" in pos:
                pos["div"] *= keep
            pos["shares"] -= n
        else:
            del acc["positions"][s["code"]]
    for b in p["buys"]:
        o = price_on(px.get(sym.get(b["code"])), day, "open", exact=True)
        pos = acc["positions"].get(b["code"])
        if not o or (pos is None) == bool(b.get("add")):   # 一般買進不買已持有的；加碼（add，假設 E1）只加在還抱著的
            continue
        budget = min(b["amount"], acc["cash"])
        shares = math.floor(budget / (o * (1 + C.FEE_RATE)))
        while shares > 0 and shares * o + fee(shares * o) > acc["cash"]:
            shares -= 1
        if shares <= 0 or shares * o < MIN_ORDER / 2:
            continue
        f = fee(shares * o)
        cost = shares * o + f
        acc["cash"] -= cost
        acc["fees"] += f
        if pos:   # 加碼：進場日與已領股利不動，進場價改成股數加權的平均成交價
            pos["price"] = round((pos["price"] * pos["shares"] + o * shares) / (pos["shares"] + shares), 2)
            pos["shares"] += shares
            pos["cost"] = round(pos["cost"] + cost, 2)
        else:
            acc["positions"][b["code"]] = {"shares": shares, "price": round(o, 2), "cost": round(cost, 2), "date": day,
                                           "reason": b["reason"]}
        acc["trades"].append({"date": day, "side": "買", "code": b["code"], "name": names.get(b["code"], ""),
                              "shares": shares, "price": round(o, 2), "fee": round(f), "reason": b["reason"],
                              **({"partial": True} if pos else {})})
    acc["pending"] = None


def credit_dividends(acc: dict, day: str, px: dict, sym: dict):
    """除息日把現金股利記進現金：前一天收盤還抱著的股數 × 每股現金股利。

    只有股價序列帶 "div" 欄位（研究框架的長歷史資料）時才有作用；模擬帳戶與一般回測的資料沒有這一欄，等於沒這一步。
    要在當天成交之前呼叫：除息日當天才買的不配息，除息日開盤賣掉的仍然配息。
    """
    for code, pos in acc["positions"].items():
        s = px.get(sym.get(code))
        if not s or "div" not in s:
            continue
        i = bisect_right(s["dates"], day) - 1
        if i < 0 or s["dates"][i] != day or not s["div"][i]:
            continue
        cash = pos["shares"] * s["div"][i]
        acc["cash"] += cash
        acc["dividends"] = acc.get("dividends", 0.0) + cash
        pos["div"] = pos.get("div", 0.0) + cash  # 這筆持股進場以來累計領到的現金股利


def market_value(acc: dict, day: str, px: dict, sym: dict) -> float:
    total = 0.0
    for code, pos in acc["positions"].items():
        c = price_on(px.get(sym.get(code)), day) or pos["price"]
        total += pos["shares"] * c
    return total


def advance(state: dict, trade_dates: list[str], px: dict, sym: dict, names: dict):
    """處理上次決策日之後、到最後一個交易日為止的每一天：成交、結算。"""
    last = state["last_decision"]
    if last is None:
        return
    for day in [d for d in trade_dates if d > last]:
        if state["status"] == "done":
            break
        started = any(a.get("pending") for a in state["accounts"].values()) or state["start"]
        if not started:
            continue
        if state["start"] is None:
            state["start"] = day
        for acc in state["accounts"].values():
            credit_dividends(acc, day, px, sym)
            _fill(acc, day, px, sym, names)
            eq = acc["cash"] + market_value(acc, day, px, sym)
            acc["equity"] = [e for e in acc["equity"] if e["date"] != day] + [{"date": day, "equity": round(eq)}]
        state["days"].append(day)
        if len(state["days"]) >= C.TRADING_DAYS:
            state["status"], state["end"] = "done", day


def _held_days(state: dict, since: str) -> int:
    return sum(1 for d in state["days"] if d >= since)


def plan_orders(state: dict, mid: str, acc: dict, ranking: list[dict], day: str, px: dict, sym: dict,
                expo: float = 1.0) -> dict:
    method = next(m for m in C.METHODS if m["id"] == mid)
    held = acc["positions"]
    ranked = [r["code"] for r in ranking]
    reason = {r["code"]: r["reason"] for r in ranking}
    votes = {r["code"]: r.get("votes") for r in ranking}
    sells = []
    exit_rules = any(k in method for k in ("stop_loss", "take_profit", "max_hold"))
    if exit_rules:
        for code, pos in held.items():
            c = price_on(px.get(sym.get(code)), day) or pos["price"]
            chg = (c / pos["price"] - 1) * 100
            if method.get("stop_loss") is not None and chg <= method["stop_loss"]:
                sells.append({"code": code, "reason": f"跌 {chg:.1f}%，觸發 {method['stop_loss']}% 停損"})
            elif method.get("take_profit") is not None and chg >= method["take_profit"]:
                sells.append({"code": code, "reason": f"漲 {chg:+.1f}%，觸發 +{method['take_profit']}% 停利"})
            elif method.get("max_hold") and _held_days(state, pos["date"]) >= method["max_hold"]:
                sells.append({"code": code, "reason": f"已持有 {method['max_hold']} 個交易日，依方法出場"})
    every = method.get("rebalance_every")
    rebalance_day = not every or not held or len(state["days"]) % every == 0
    if exit_rules and not method.get("rank_exit"):
        pass
    elif not rebalance_day:
        pass  # 不是換股日：只處理停損
    elif mid == "trust":
        hold = method.get("hold_days", 11)
        for code, pos in held.items():
            if _held_days(state, pos["date"]) >= hold:
                sells.append({"code": code, "reason": f"已持有 {hold} 個交易日，依方法出場"})
    elif ranking or mid == "ai_theme":
        keep = set(ranked if mid == "ai_theme" else ranked[:C.KEEP_RANK])
        already = {s["code"] for s in sells}
        for code in held:
            if code not in keep and code not in already and _held_days(state, held[code]["date"]) >= method.get("min_hold", 0):
                if mid == "ai_theme":
                    why = "近 5 天 AI 推理沒再提到"
                elif mid == "claude":
                    why = (f"共識轉弱：現在只剩 {votes[code]} 種方法看好，排第 {ranked.index(code) + 1} 名，掉出前 {C.KEEP_RANK} 名，換成更多方法看好的股票"
                           if code in reason else "共識轉弱：今天已經沒有任何方法把它排進前 5 名，換股")
                else:
                    why = "已不在前 %d 名" % C.KEEP_RANK
                sells.append({"code": code, "reason": why})
    sold = {s["code"] for s in sells}
    remain = [c for c in held if c not in sold]
    equity = acc["cash"] + market_value(acc, day, px, sym)
    invested = sum(held[c]["shares"] * (price_on(px.get(sym.get(c)), day) or held[c]["price"]) for c in remain)
    # 綜合帳戶：持股比例降低時，先賣排名最後的
    target_total = equity * expo
    # 假設 E1（只有研究變體帶旗標、而且只作用在 combo）：改成每檔賣同樣的比例，比例回升時再等比例補回
    prop = bool((state.get("variant") or {}).get("proportional_trim")) and mid == "combo"
    value = lambda c: held[c]["shares"] * (price_on(px.get(sym.get(c)), day) or held[c]["price"])  # noqa: E731
    if prop and expo > 0 and rebalance_day and invested > target_total * 1.1:
        frac = 1 - target_total / invested   # 沿用既有的 +10% 觸發帶；一次減到目標值
        for code in remain:
            n = math.floor(held[code]["shares"] * frac)
            if n > 0:
                sells.append({"code": code, "shares": n, "reason": f"降低持股比例：每檔等比例減碼 {frac * 100:.1f}%"})
                invested -= n * value(code) / held[code]["shares"]
    elif expo > 0 and rebalance_day and invested > target_total * 1.1:
        for code in sorted(remain, key=lambda c: ranked.index(c) if c in ranked else 999, reverse=True):
            if invested <= target_total * 1.05:
                break
            v = held[code]["shares"] * (price_on(px.get(sym.get(code)), day) or held[code]["price"])
            invested -= v
            remain.remove(code)
            sells.append({"code": code, "reason": "降低持股比例"})
    cash = acc["cash"] + sum(s.get("shares", held[s["code"]]["shares"]) * (price_on(px.get(sym.get(s["code"])), day) or 0) * 0.995
                             for s in sells)
    slots = C.TOP_N - len(remain) if rebalance_day else 0
    per = equity * expo / C.TOP_N
    buys = []
    room = max(0.0, target_total - invested)
    for code in ranked[:C.TOP_N]:
        if slots <= 0:
            break
        if code in held:
            continue
        amt = min(per, cash, room)
        if amt < MIN_ORDER:
            break
        buys.append({"code": code, "amount": round(amt), "reason": reason[code]})
        cash -= amt
        room -= amt
        slots -= 1
    if prop and expo > 0 and rebalance_day and remain and 0 < invested < target_total * 0.9:
        # 沿用既有的 -10% 觸發帶。空著的檔位照舊留給新股（每檔 per），其餘缺口才補回既有持股；不超過剩下的現金
        gap = min(target_total - invested - (C.TOP_N - len(remain)) * per, cash)
        if gap >= MIN_ORDER:
            for code in remain:
                buys.append({"code": code, "add": True, "amount": round(gap * value(code) / invested),
                             "reason": f"持股比例回升：每檔等比例補回 {gap / invested * 100:.1f}%"})
    return {"decided": day, "sells": sells, "buys": buys}


def decide(state: dict, ctx: dict, day: str, px: dict, sym: dict, names: dict) -> dict:
    """依各方法選股、產生委託，並寫進選股日誌。回傳 {方法: 排名}。"""
    rankings = {}
    expo, expo_note = exposure(ctx.get("regime") or {})
    for m in sorted(C.METHODS, key=lambda m: m["id"] in ("claude", "claude2")):  # Claude 判斷最後做，要用到其他方法的結果
        mid = m["id"]
        try:
            if mid in ("claude", "claude2"):
                ctx["rankings"] = rankings
                ctx["perf"] = ctx["perf_fn"](state) if ctx.get("perf_fn") else {}
            ranking = METHOD_FNS[mid](ctx)
        except Exception as e:  # noqa: BLE001 單一方法壞掉不影響其他
            ranking = []
            ctx.setdefault("warnings", []).append(f"{m['name']} 選股失敗：{e}")
        rankings[mid] = ranking
        acc = state["accounts"][mid]
        e = expo if mid in ("combo", "claude", "claude2") else 1.0
        note = expo_note if mid in ("claude", "claude2") else ""
        mf = m.get("market_filter")
        if mf and (ctx.get("regime") or {}).get(f"above_ma{mf}") is False:
            e, note = 0.0, "大盤在年線之下，依方法不買新股（持股照規則續抱）"
        acc["pending"] = plan_orders(state, mid, acc, ranking, day, px, sym, e)
        state["journal"].append({
            "date": day, "method": mid,
            "picks": [{"code": r["code"], "name": names.get(r["code"], ""), "reason": r["reason"]} for r in ranking[:C.TOP_N]],
            "buys": [b["code"] for b in acc["pending"]["buys"]],
            "sells": [{"code": s["code"], "name": names.get(s["code"], ""), "reason": s["reason"]} for s in acc["pending"]["sells"]],
            "note": expo_note if mid == "combo" else (ctx.get(f"{mid}_note") or note) if mid in ("claude", "claude2") else note or ("" if ranking else "今天沒有符合條件的股票或資料抓不到，維持原持股"),
        })
    return rankings


def run_day(state: dict, ctx: dict, trade_dates: list[str], px: dict, sym: dict, names: dict) -> dict:
    """處理一次排程。trade_dates 是到決策日為止的交易日（舊到新）。"""
    day = trade_dates[-1]
    if state["last_decision"] and day < state["last_decision"]:
        return state
    if state["last_decision"] == day and state.get("checkpoint"):
        keep = {"chips_cache": state.get("chips_cache"), "ai_hist": state.get("ai_hist")}
        state = {**state["checkpoint"], **keep}
    for m in C.METHODS:  # 新增的方法：開一個新帳戶
        state["accounts"].setdefault(m["id"], new_account())
    checkpoint = copy.deepcopy({k: v for k, v in state.items() if k != "checkpoint"})
    advance(state, trade_dates, px, sym, names)
    state["journal"] = [j for j in state["journal"] if j["date"] != day]
    if state["status"] != "done":
        decide(state, ctx, day, px, sym, names)
    state["last_decision"] = day
    state["checkpoint"] = checkpoint
    return state
