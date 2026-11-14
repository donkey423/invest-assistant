"""研究框架的執行器：用真正的引擎（engine.run_day）逐日重跑樣本內期間，分折計算績效。

所有研究（含 baseline）都套用的修正（不是假設，是修 AUDIT.md 列出的錯誤）：
- VIX 只用日期早於決策日的最近一筆（backtest.vix_before）。
- 現金股利在除息日入帳（engine.credit_dividends，資料帶 "div" 欄位才有作用）。
- 期末還沒賣的持股，以收盤價扣掉賣出成本（手續費＋證交稅）計值。
- 景氣燈號仍寫死紅燈（係數 1.0）：沒有歷史資料，屬「未驗證參數」。

Walk-forward：所有假設的數值都是事先固定、不在資料上調參，所以這裡的 walk-forward 是
「帳戶從樣本內第一天連續跑到最後一天，再把評估期切成 5 個相連不重疊的折，逐折看績效」。
"""
from __future__ import annotations

import copy
import hashlib
import json
import logging
import subprocess
from statistics import median
from bisect import bisect_left, bisect_right
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from .. import backtest as bt
from .. import config as C
from .. import engine, metrics
from ..__main__ import TW, universe
from .dataset import manifest_hash

log = logging.getLogger("papertrade.research")

METHOD_IDS = ["momentum", "graham", "combo", "oneil", "tech4"]   # 四塊研究對象用到的方法（不含 Claude 判斷、AI 主題）
LOOKBACK = 320    # 每天只給選股方法最近幾根 K 棒。目前最長的回看是 12-1 動能的 253 根、歐尼爾的 252 根
FOLDS = 5
TR_BENCH = "0050.TW"   # 另外算含息報酬的對照

# 變體登記表。baseline＝完全不改。每個假設在自己的分支加一筆，例如：
#   "M1": {"methods": {"momentum": {"market_filter": 200}}}
# 保留鍵：
#   "methods"  {方法 id: {設定鍵: 值}}，執行期間蓋在 C.METHODS 的深層複本上，跑完還原。
#   "lookback" 每天給選股方法的 K 棒數（預設 LOOKBACK；None＝全部歷史，給需要擴張視窗的假設用）。
# 其他鍵都是自訂旗標，整個 dict 會放在 ctx["variant"]（選股方法讀）與 state["variant"]（engine.plan_orders 讀）。
VARIANTS: dict[str, dict] = {
    "baseline": {},
    # 假設 S2：oneil、tech4 的停損門檻由固定 -8% 改為 −5 × 進場決策日前 60 筆日報酬的標準差（engine.vol_stop，進場時固定）
    "S2": {"vol_scaled_stop": True},
}


def variant_hash(flags: dict) -> str:
    """旗標內容的識別碼（和變體名稱、程式版本無關）。"""
    return hashlib.sha256(json.dumps(flags, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:12]


def code_version() -> str:
    try:
        root = Path(__file__).resolve().parents[2]
        return subprocess.run(["git", "rev-parse", "--short=12", "HEAD"], cwd=root, capture_output=True, text=True,
                              timeout=10, check=True).stdout.strip() or "unknown"
    except Exception:  # noqa: BLE001 沒有 git 也能跑
        return "unknown"


@contextmanager
def patched_config(flags: dict):
    """執行期間把 C.METHODS 換成「只含研究方法、已套用變體設定」的深層複本，並取消天數上限；離開時還原。"""
    keep_methods, keep_days = C.METHODS, C.TRADING_DAYS
    methods = [copy.deepcopy(m) for m in keep_methods if m["id"] in METHOD_IDS]
    for mid, over in (flags.get("methods") or {}).items():
        target = next((m for m in methods if m["id"] == mid), None)
        if target is None:
            raise ValueError(f"變體設定指到不在研究範圍的方法：{mid}")
        target.update(copy.deepcopy(over))
    C.METHODS, C.TRADING_DAYS = methods, 10 ** 9
    try:
        yield methods
    finally:
        C.METHODS, C.TRADING_DAYS = keep_methods, keep_days


# ---------- 逐日資料 ----------

def window_px(px: dict, day: str, lookback: int | None = LOOKBACK) -> dict:
    """到 day 為止的股價；lookback 有值時只留每檔最後 lookback 根（結果和全部歷史相同，快很多）。"""
    out = {}
    for k, s in px.items():
        n = bisect_right(s["dates"], day)
        a = max(0, n - lookback) if lookback else 0
        out[k] = {f: v[a:n] for f, v in s.items()}
    return out


def revenue_tables(rev: dict) -> dict:
    """每檔預先算好「可用日 → 當時的月營收摘要」，逐日用二分搜尋查（結果和 backtest.revenue_on 相同）。"""
    out = {}
    for code, series in rev.items():
        yms = sorted(series)
        out[code] = ([bt._avail(ym) for ym in yms], [bt.revenue_on(series, bt._avail(ym)) for ym in yms])
    return out


def revenue_at(tables: dict, code: str, day: str) -> dict | None:
    t = tables.get(code)
    if not t:
        return None
    i = bisect_right(t[0], day) - 1
    return t[1][i] if i >= 0 else None


def value_at(col: dict | None, day: str) -> dict | None:
    """欄位式估值資料在 day 當天以前最近一筆（結果和 backtest.value_on 相同）。"""
    if not col or not col["dates"]:
        return None
    i = bisect_right(col["dates"], day) - 1
    if i < 0:
        return None
    return {"pe": col["pe"][i] or None, "yield": col["dy"][i], "pb": col["pb"][i] or None}


def folds(n: int, k: int = FOLDS) -> list[tuple[int, int]]:
    """把 n 個評估日切成 k 個相連、不重疊、長度盡量相等的折：[(起, 迄不含)]。餘數分給前面的折。"""
    k = max(1, min(k, n))
    size, extra = divmod(n, k)
    out, a = [], 0
    for i in range(k):
        b = a + size + (1 if i < extra else 0)
        out.append((a, b))
        a = b
    return out


# ---------- 模擬 ----------

def simulate(ds: dict, flags: dict, start_decision: str, uni=None) -> dict:
    """從 start_decision 收盤第一次選股，逐日跑到資料最後一天。

    回傳 {"dates": 評估日, "methods": {id: {equity, trades, positions, exposure, dividends, exit_cost}}, "regime": [...]}。
    每天跑完就把淨值與交易紀錄搬出 state：引擎不會回頭讀它們，搬走後每天的 checkpoint 深層複製才不會越跑越慢。
    """
    sym, names, chain_of = uni or universe()
    cal = bt.calendar(ds["px"])
    i0 = bisect_left(cal, start_decision)
    lookback = flags.get("lookback", LOOKBACK)
    tables = revenue_tables(ds["rev"])
    memo: dict = {}   # 同一次執行跨日共用的暫存，給需要累積統計（例如擴張視窗中位數）的假設用
    with patched_config(flags) as methods:
        ids = [m["id"] for m in methods]
        rec = {mid: {"equity": [], "trades": [], "positions": [], "exposure": [], "dividends": []} for mid in ids}
        if flags.get("vol_scaled_stop"):   # 假設 S2 的診斷：固定門檻會停損、新門檻不停損的事件
            for mid in engine.STOP_VARIANT_METHODS:
                if mid in rec:
                    rec[mid]["stop_events"] = []
        regime, px = [], {}
        state = engine.new_state()
        state["variant"] = flags
        for i in range(i0, len(cal)):
            day = cal[i]
            dates = cal[max(0, i - 9):i + 1]   # 引擎只需要上次決策日之後的交易日，法人只看近 5 天
            px = window_px(ds["px"], day, lookback)
            rev = {c: r for c in sym if (r := revenue_at(tables, c, day))}
            val = {c: v for c in sym if (v := value_at(ds["val"].get(c), day))}
            ctx = bt.day_ctx(ds, sym, chain_of, dates, px, rev=rev, val=val)
            ctx["variant"], ctx["memo"] = flags, memo
            state = engine.run_day(state, ctx, dates, px, sym, names)
            state["checkpoint"], state["journal"] = None, []
            for ev in state.pop("stop_diag", []):
                rec[ev["method"]]["stop_events"].append({**ev, "symbol": sym.get(ev["code"])})
            for mid in ids:
                acc, r = state["accounts"][mid], rec[mid]
                r["trades"].extend(acc["trades"])
                acc["trades"] = []
                if not acc["equity"]:
                    continue
                eq = acc["equity"][-1]["equity"]
                acc["equity"] = []
                r["equity"].append(eq)
                r["positions"].append(len(acc["positions"]))
                r["exposure"].append(engine.market_value(acc, day, px, sym) / eq if eq else 0.0)
                r["dividends"].append(round(acc.get("dividends", 0.0), 2))
            if i > i0:
                g = ctx["regime"]
                regime.append({"below_ma60": g["above_ma60"] is False, "below_ma200": g["above_ma200"] is False,
                               "vix25": g["vix"] is not None and g["vix"] >= 25})
        last = cal[-1]
        for mid in ids:   # 期末持股：收盤價扣掉賣出成本
            acc, cost = state["accounts"][mid], 0.0
            for code, pos in acc["positions"].items():
                v = pos["shares"] * (engine.price_on(px.get(sym.get(code)), last) or pos["price"])
                cost += engine.fee(v) + v * C.TAX_RATE
            rec[mid]["exit_cost"] = round(cost)
            rec[mid]["name"] = next(m["name"] for m in methods if m["id"] == mid)
    days = cal[i0 + 1:]
    for mid, r in rec.items():
        if len(r["equity"]) != len(days):
            raise RuntimeError(f"{mid} 的淨值筆數 {len(r['equity'])} 和評估日數 {len(days)} 對不上")
    return {"dates": days, "methods": rec, "regime": regime}


# ---------- 績效 ----------

def _period(r: dict, dates: list[str], a: int, b: int, last: bool) -> dict:
    """某方法在評估日 [a, b) 的績效。last=True 時最後一天的淨值扣掉期末持股的賣出成本。"""
    eq = [r["equity"][a - 1] if a else C.START_CASH, *r["equity"][a:b]]
    if last and b > a:
        eq[-1] -= r["exit_cost"]
    lo, hi = dates[a], dates[b - 1]
    trades = [t for t in r["trades"] if lo <= t["date"] <= hi]
    div0 = r["dividends"][a - 1] if a else 0.0
    return {**metrics.summarize(eq, trades),
            "avg_positions": sum(r["positions"][a:b]) / (b - a), "avg_exposure": sum(r["exposure"][a:b]) / (b - a),
            "stop_exits": sum(1 for t in trades if t["side"] == "賣" and "停損" in t.get("reason", "")),
            "dividends": round(r["dividends"][b - 1] - div0), "exit_cost": r["exit_cost"] if last else 0,
            "sr_period": metrics.sharpe(metrics.daily_returns(eq), periods=1)}


def bench_curves(ds: dict, start_decision: str, dates: list[str]) -> dict:
    """對照用的淨值曲線（起點 START_CASH，第 0 點是 start_decision 收盤）：大盤價格指數、0050 含息。"""
    out = {}
    tw = ds["px"].get("^TWII")
    if tw:
        base = engine.price_on(tw, start_decision)
        if base:
            out["^TWII"] = {"name": "台股加權指數（不含息）",
                            "equity": [C.START_CASH * (engine.price_on(tw, d) or base) / base for d in [start_decision, *dates]]}
    s = ds["px"].get(TR_BENCH)
    if s:
        v, curve, i = float(C.START_CASH), [], bisect_right(s["dates"], start_decision)
        div = s.get("div") or [0.0] * len(s["dates"])
        if i:
            curve.append(v)
            for d in dates:
                while i < len(s["dates"]) and s["dates"][i] <= d:
                    v *= (s["close"][i] + div[i]) / s["close"][i - 1]
                    i += 1
                curve.append(v)
            out[TR_BENCH + ":TR"] = {"name": "元大台灣50（含息再投入）", "equity": curve}
    return out


def spared_stops(events: list[dict], trades: list[dict], px: dict, start: str, end: str) -> dict:
    """假設 S2 的診斷：日期在 [start, end] 內、「固定 -8% 會停損、新門檻不停損」的事件，以及該部位之後的報酬。

    同一筆持股連續好幾天都符合時只記第一天。「之後的報酬」的起點是固定門檻的出場價（事件隔天開盤），
    終點是這筆持股實際出場的成交價（到 end 還沒出場就用 end 的收盤價），中間除息的每股現金股利加回去；不扣交易成本。
    只用到 end 為止的資料，所以樣本內的診斷不會碰到保留段。
    """
    out, seen = [], set()
    for ev in events:
        key = (ev["code"], ev["entry"])
        if key in seen or not start <= ev["date"] <= end:
            continue
        seen.add(key)
        s = px.get(ev["symbol"]) or {"dates": [], "open": [], "close": []}
        i = bisect_right(s["dates"], ev["date"])   # 事件之後的第一根 K 棒＝固定門檻的出場日
        row = {k: ev[k] for k in ("date", "code", "entry", "chg", "stop")}
        row.update({"exit_date": None, "exit_reason": None, "after_return": None})
        if i < len(s["dates"]) and s["dates"][i] <= end and s["open"][i]:
            sell = next((t for t in trades if t["side"] == "賣" and t["code"] == ev["code"] and t.get("held_from") == ev["entry"]
                         and ev["date"] < t["date"] <= end), None)
            j = bisect_right(s["dates"], sell["date"] if sell else end) - 1
            price = sell["price"] if sell else s["close"][j]
            divs = sum((s.get("div") or [0.0] * len(s["dates"]))[i + 1:j + 1])   # 固定門檻出場日當天除息的，兩邊都領得到，不算
            row.update({"exit_date": sell["date"] if sell else None, "exit_reason": sell["reason"] if sell else "期末仍持有",
                        "after_return": (price + divs) / s["open"][i] - 1})
        out.append(row)
    rets = [r["after_return"] for r in out if r["after_return"] is not None]
    return {"count": len(out), "mean_after_return": sum(rets) / len(rets) if rets else None, "events": out}


def vol_stop_diag(r: dict, px: dict, start: str, end: str) -> dict:
    """假設 S2 的診斷：期間內的停損出場筆數、進場時用的門檻分布（%）、被固定門檻停損但新門檻不停損的事件。"""
    trades = [t for t in r["trades"] if start <= t["date"] <= end]
    stops = [t["stop"] for t in trades if t["side"] == "買" and "stop" in t]
    return {"stop_exits": sum(1 for t in trades if t["side"] == "賣" and "停損" in t.get("reason", "")),
            "thresholds": {"n": len(stops), "fallback": sum(1 for t in trades if t.get("stop_fallback")),
                           "min": min(stops, default=None), "median": median(stops) if stops else None, "max": max(stops, default=None)},
            "spared": spared_stops(r["stop_events"], r["trades"], px, start, end)}


def evaluate(sim: dict, ds: dict, start_decision: str, k: int = FOLDS, holdout_start: str | None = None) -> dict:
    """把模擬結果整理成各期間的績效：全樣本內（all）、各折（folds），解鎖時另有保留段（holdout）。"""
    dates = sim["dates"]
    n_in = bisect_left(dates, holdout_start) if holdout_start else len(dates)
    spans = folds(n_in, k)
    n = len(dates)
    span_info = lambda a, b: {"start": dates[a], "end": dates[b - 1], "days": b - a}  # noqa: E731
    gates = lambda a, b: {key: sum(g[key] for g in sim["regime"][a:b]) for key in ("below_ma60", "below_ma200", "vix25")}  # noqa: E731
    out = {"period": span_info(0, n_in), "folds": [span_info(a, b) for a, b in spans],
           "regime": {"all": gates(0, n_in), "folds": [gates(a, b) for a, b in spans]},
           "methods": {}, "benchmarks": {}, "dates": dates}
    if n_in < n:
        out["holdout_period"] = span_info(n_in, n)
        out["regime"]["holdout"] = gates(n_in, n)
    for mid, r in sim["methods"].items():
        m = {"name": r["name"], "all": _period(r, dates, 0, n_in, n_in == n),
             "folds": [_period(r, dates, a, b, b == n) for a, b in spans],
             "equity": r["equity"], "trades": r["trades"]}
        if "stop_events" in r:
            m["vol_stop"] = vol_stop_diag(r, ds["px"], dates[0], dates[n_in - 1])
        if n_in < n:
            m["holdout"] = _period(r, dates, n_in, n, True)
            if "stop_events" in r:
                m["holdout"]["vol_stop"] = vol_stop_diag(r, ds["px"], dates[n_in], dates[-1])
        out["methods"][mid] = m
    for key, bc in bench_curves(ds, start_decision, dates).items():
        cut = lambda a, b, e=bc["equity"]: metrics.summarize(e[a:b + 1], [])  # noqa: E731 曲線第 0 點是起點，所以位移一格
        out["benchmarks"][key] = {"name": bc["name"], "all": cut(0, n_in), "folds": [cut(a, b) for a, b in spans],
                                  **({"holdout": cut(n_in, n)} if n_in < n else {})}
    return out


def run_variant(name: str, ds: dict, manifest: dict, k: int = FOLDS, uni=None, unlocked: bool = False) -> dict:
    """跑一個變體，回傳完整結果（還沒寫檔）。"""
    if name not in VARIANTS:
        raise KeyError(f"沒有登記的變體：{name}（已登記：{'、'.join(VARIANTS)}）")
    flags = VARIANTS[name]
    sim = simulate(ds, flags, manifest["warmup_end"], uni=uni)
    res = evaluate(sim, ds, manifest["warmup_end"], k, manifest["holdout_start"] if unlocked else None)
    return {"variant": name, "flags": flags, "hash": variant_hash(flags), "code": code_version(),
            "dataset": manifest_hash(manifest), "synthetic": bool(manifest.get("synthetic")), "holdout_unlocked": unlocked,
            "generated_at": datetime.now(TW).isoformat(timespec="minutes"), "start_cash": C.START_CASH,
            "lookback": flags.get("lookback", LOOKBACK), **res}
