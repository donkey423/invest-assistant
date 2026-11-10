"""回測：用現在這套方法（含 Claude 判斷），逐日重跑過去 3 個月與 6 個月，跟大盤比。

python -m papertrade.backtest [--out site/data]

避免偷看未來：
- 每天只用「當天收盤以前」的股價；隔天開盤價成交（和模擬帳戶同一套引擎）。
- 月營收：M 月營收視為 M+1 月 11 日起才知道（法規是 10 日前公布）。
- 法人買賣超：證交所每天的 T86（只有上市股；上櫃股沒有法人資料）。
- 本益比／殖利率／淨值比：FinMind 每日資料，只用當天以前最近一筆。
- 產業鏈燈號：上游訊號沒有歷史紀錄，回測只用「月營收是否加速」判斷。
- AI 讀新聞推理沒有歷史紀錄，回測不含這個方法。
- 景氣燈號：國發會 2025/12–2026/09 連續紅燈，回測期間一律視為紅燈。
已知偏差：選股範圍是現在的產業鏈代表股（事後挑的），會讓所有方法的結果偏好看，要和大盤比、方法之間互相比較才有意義。
"""
from __future__ import annotations

import argparse
import copy
import json
import logging
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from briefing import config as bcfg
from briefing.signals import chain_light

from . import config as C
from . import data, engine, summary
from .__main__ import TW, cut, method_perf, universe

log = logging.getLogger("papertrade.backtest")
FINMIND = "https://api.finmindtrade.com/api/v4/data?dataset={ds}&data_id={code}&start_date={start}"
WINDOWS = [(63, "近 3 個月"), (126, "近 6 個月")]
OUT_FILE = "backtest.json"


def history_long(symbols):
    import yfinance as yf  # 延後匯入

    df = yf.download(list(symbols), period="2y", interval="1d", auto_adjust=False,
                     group_by="ticker", progress=False, threads=True)
    out = {}
    for sym in symbols:
        try:
            s = df[sym][["Open", "Close", "Volume"]].dropna()
            out[sym] = {"dates": [d.strftime("%Y-%m-%d") for d in s.index],
                        "open": [float(v) for v in s["Open"].values],
                        "close": [float(v) for v in s["Close"].values],
                        "volume": [float(v) for v in s["Volume"].values]}
        except Exception as e:  # noqa: BLE001
            log.warning("抓不到 %s：%s", sym, e)
    return out


def finmind(ds: str, code: str, start: str, get=data.get_json) -> list[dict]:
    try:
        r = get(FINMIND.format(ds=ds, code=code, start=start))
        return r.get("data") or [] if isinstance(r, dict) else []
    except Exception as e:  # noqa: BLE001
        log.warning("FinMind %s %s 失敗：%s", ds, code, e)
        return []


def revenue_series(rows: list[dict]) -> dict[str, float]:
    """FinMind 月營收 → {'2026-09': 營收}。"""
    out = {}
    for r in rows:
        try:
            out[f"{int(r['revenue_year']):04d}-{int(r['revenue_month']):02d}"] = float(r["revenue"])
        except (KeyError, TypeError, ValueError):
            continue
    return out


def _avail(ym: str) -> str:
    """M 月營收最早可用的日期：M+1 月 11 日。"""
    y, m = int(ym[:4]), int(ym[5:])
    y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    return f"{y:04d}-{m:02d}-11"


def revenue_on(series: dict[str, float], day: str) -> dict | None:
    known = sorted(ym for ym in series if _avail(ym) <= day)
    if not known:
        return None
    ym = known[-1]
    y, m = int(ym[:4]), int(ym[5:])
    last = f"{y - 1:04d}-{m:02d}"
    if last not in series or not series[last]:
        return None
    yoy = (series[ym] / series[last] - 1) * 100
    cur = [series.get(f"{y:04d}-{i:02d}") for i in range(1, m + 1)]
    prev = [series.get(f"{y - 1:04d}-{i:02d}") for i in range(1, m + 1)]
    ytd = (sum(cur) / sum(prev) - 1) * 100 if None not in cur and None not in prev and sum(prev) else None
    return {"ym": ym, "yoy": round(yoy, 2), "ytd_yoy": round(ytd, 2) if ytd is not None else None}


def value_on(rows: list[dict], day: str) -> dict | None:
    best = None
    for r in rows:
        if r.get("date", "") <= day:
            best = r
        else:
            break
    if not best:
        return None
    f = lambda k: float(best[k]) if best.get(k) not in (None, "") else None  # noqa: E731
    return {"pe": f("PER") or None, "yield": f("dividend_yield"), "pb": f("PBR") or None}


def chain_lights(rev: dict) -> dict:
    out = {}
    for ch in bcfg.CHAINS:
        acc = []
        for s in ch["stocks"]:
            r = rev.get(s["symbol"].split(".")[0])
            if r and r.get("yoy") is not None and r.get("ytd_yoy") is not None:
                acc.append(r["yoy"] - r["ytd_yoy"])
        acc.sort()
        med = (acc[len(acc) // 2] if len(acc) % 2 else (acc[len(acc) // 2 - 1] + acc[len(acc) // 2]) / 2) if acc else None
        light, why = chain_light([], med, bcfg)
        out[ch["id"]] = {"light": light, "name": ch["name"], "why": why}
    return out


def load(sym: dict, cal_start: str, get=data.get_json, history_fn=history_long, chip_dates=None) -> dict:
    px = history_fn([*sym.values(), *(b["symbol"] for b in C.BENCHMARKS), "^VIX"])
    start_rev = (date.fromisoformat(cal_start) - timedelta(days=800)).isoformat()
    start_val = (date.fromisoformat(cal_start) - timedelta(days=14)).isoformat()
    rev, val = {}, {}
    for code in sym:
        rev[code] = revenue_series(finmind("TaiwanStockMonthRevenue", code, start_rev, get))
        val[code] = sorted(finmind("TaiwanStockPER", code, start_val, get), key=lambda r: r.get("date", ""))
        time.sleep(0.3)
    chips = {}
    for d in chip_dates or []:
        try:
            rows = data.parse_t86(get(data.T86_URL.format(d=d.replace("-", ""))))
            if rows:
                chips[d] = rows
        except Exception as e:  # noqa: BLE001
            log.warning("T86 %s 失敗：%s", d, e)
        time.sleep(1.2)
    return {"px": px, "rev": rev, "val": val, "chips": chips}


def calendar(px: dict) -> list[str]:
    cal = set()
    for k in ("^TWII", "0050.TW", "2330.TW"):
        cal |= set((px.get(k) or {}).get("dates") or [])
    return sorted(cal)


def run_window(d: dict, sym, names, chain_of, cal: list[str], n_days: int) -> dict:
    window = cal[-n_days - 1:]  # 第一天收盤選股，之後 n_days 天成交
    keep_methods, keep_days = C.METHODS, C.TRADING_DAYS
    C.METHODS = [m for m in keep_methods if m["id"] != "ai_theme"]
    C.TRADING_DAYS = 10_000
    try:
        state = engine.new_state()
        for day in window:
            i = cal.index(day)
            dates = cal[:i + 1]
            px = cut(d["px"], day)
            tw = px.get("^TWII", {}).get("close") or []
            rev = {c: r for c in sym if (r := revenue_on(d["rev"].get(c) or {}, day))}
            chip_dates = [x for x in dates[-5:] if x in d["chips"]]
            ma = lambda n: sum(tw[-n:]) / n if len(tw) >= n else None  # noqa: E731
            vix = (px.get("^VIX") or {}).get("close") or [None]
            ctx = {
                "date": day, "codes": list(sym), "sym": sym, "px": px, "chain_of": chain_of,
                "chains": chain_lights(rev), "revenue": rev, "chips": d["chips"] if chip_dates and chip_dates[-1] == day else {},
                "chip_dates": chip_dates, "value": {c: v for c in sym if (v := value_on(d["val"].get(c) or [], day))},
                "ai_watch": [], "warnings": [],
                "regime": {"light": "紅燈", "above_ma60": tw[-1] >= ma(60) if ma(60) else None,
                           "above_ma200": tw[-1] >= ma(200) if ma(200) else None, "vix": vix[-1]},
            }
            ctx["perf_fn"] = lambda st, px=px, dates=dates: method_perf(st, px, sym, dates)
            state = engine.run_day(state, ctx, dates, px, sym, names)
            state["checkpoint"] = None  # 回測不需要重跑還原，省記憶體
        px = cut(d["px"], window[-1])
        res = summary.build(state, px, sym, names, window, {"regime": {}}, "")
    finally:
        C.METHODS, C.TRADING_DAYS = keep_methods, keep_days
    slim = lambda m: {k: m[k] for k in ("id", "name", "return_pct", "excess_pct", "mdd_pct", "beat_days", "days",  # noqa: E731
                                        "win_rate", "closed", "trades", "fees", "picks_hit", "equity", "rank")}
    return {"start": res["start"], "end": window[-1], "days": res["days_done"],
            "benchmarks": res["benchmarks"], "methods": [slim(m) for m in res["methods"]],
            "claude_trades": list(reversed(state["accounts"]["claude"]["trades"]))[:60]}


def main(argv=None, get=data.get_json, history_fn=history_long, now=None) -> dict:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="site/data")
    args = ap.parse_args(argv)
    now = now or datetime.now(TW)
    sym, names, chain_of = universe()
    px_probe = history_fn([*sym.values(), *(b["symbol"] for b in C.BENCHMARKS), "^VIX"])
    cal = calendar(px_probe)
    if cal and cal[-1] == now.date().isoformat() and now.hour < 14:
        cal = cal[:-1]
    longest = max(n for n, _ in WINDOWS)
    need = cal[-longest - 6:]
    d = load(sym, need[0], get=get, history_fn=lambda s: px_probe, chip_dates=need)
    cal = [x for x in cal if x <= cal[-1]]
    out = {"generated_at": now.isoformat(timespec="minutes"), "universe_size": len(sym),
           "coverage": {"revenue": sum(1 for v in d["rev"].values() if v), "value": sum(1 for v in d["val"].values() if v),
                        "chip_days": len(d["chips"]), "stocks": len(sym)},
           "notes": [line.strip("- ").strip() for line in __doc__.split("避免偷看未來：")[1].strip().splitlines() if line.strip()],
           "windows": []}
    for n, label in WINDOWS:
        log.info("回測 %s（%d 個交易日）", label, n)
        w = run_window(d, sym, names, chain_of, cal, n)
        out["windows"].append({"label": label, **w})
    p = Path(args.out)
    p.mkdir(parents=True, exist_ok=True)
    (p / OUT_FILE).write_text(json.dumps(out, ensure_ascii=False, indent=1), "utf-8")
    for w in out["windows"]:
        log.info("== %s %s～%s", w["label"], w["start"], w["end"])
        for m in sorted(w["methods"], key=lambda m: m["rank"]):
            log.info("%2d %-12s %+7.2f%%  比大盤 %+7.2f%%  回落 %6.2f%%", m["rank"], m["name"], m["return_pct"],
                     m["excess_pct"] or 0, m["mdd_pct"])
    return out


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    main()
