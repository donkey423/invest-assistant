"""每天收盤後跑一次：python -m papertrade [--out site/data]

讀 latest.json（月營收、產業鏈燈號）與 ai_summary.json（AI 主題推理），抓日線、法人與本益比，
處理模擬帳戶後寫出 papertrade.json（網頁用）與 papertrade_state.json（帳戶狀態）。
"""
from __future__ import annotations

import argparse
import json
import logging
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path

from briefing import config as bcfg

from . import config as C
from . import data, engine, summary

TW = timezone(timedelta(hours=8))
log = logging.getLogger("papertrade")
STATE_FILE, OUT_FILE = "papertrade_state.json", "papertrade.json"
AI_KEEP_DAYS = 5


def universe():
    sym, names, chain_of = {}, {}, {}
    for ch in bcfg.CHAINS:
        for s in ch["stocks"]:
            if not s["symbol"].endswith((".TW", ".TWO")):
                continue
            code = s["symbol"].split(".")[0]
            sym[code], names[code] = s["symbol"], s["name"]
            chain_of.setdefault(code, []).append(ch["id"])
    return sym, names, chain_of


def _read(p: Path) -> dict:
    try:
        return json.loads(p.read_text("utf-8"))
    except (OSError, ValueError):
        return {}


def ai_watch(state: dict, ai: dict, trade_dates: list[str]) -> list[dict]:
    """把 AI 主題推理的觀察標的記進歷史，回傳近 AI_KEEP_DAYS 個交易日提過的台股（新到舊、不重複）。"""
    day = str(ai.get("written_at") or "")[:10]
    hist = [h for h in state.get("ai_hist") or [] if h["date"] != day]
    for t in ai.get("themes") or []:
        for w in t.get("watch") or []:
            for code in re.findall(r"(?<!\d)(\d{4})(?!\d)", str(w)):
                hist.append({"date": day, "code": code, "title": t.get("title", "")})
    if trade_dates:
        cut = trade_dates[-AI_KEEP_DAYS] if len(trade_dates) >= AI_KEEP_DAYS else trade_dates[0]
        hist = [h for h in hist if h["date"] and h["date"] >= cut and h["date"] <= _next_day(trade_dates[-1])]
    state["ai_hist"] = hist
    seen, out = set(), []
    for h in sorted(hist, key=lambda h: h["date"], reverse=True):
        if h["code"] not in seen:
            seen.add(h["code"])
            out.append(h)
    return out


def _next_day(d: str) -> str:
    """AI 摘要是早上寫的（決策日的隔天早上也算），允許到決策日後 3 天。"""
    return (datetime.fromisoformat(d) + timedelta(days=3)).date().isoformat()


def method_perf(state: dict, px: dict, sym: dict, dates: list[str]) -> dict:
    """給 Claude 判斷用：各方法的選股命中率，加上帳戶近 5 天比大盤多賺多少（%）。"""
    perf = summary.pick_hits(state, px, sym, dates)
    tw = (summary.bench_series(state, px).get("^TWII") or {}).get("equity") or []
    for mid, acc in state["accounts"].items():
        eq = acc.get("equity") or []
        if len(eq) >= 2 and len(tw) >= 2:
            k = min(5, len(eq) - 1, len(tw) - 1)
            a = eq[-1]["equity"] / eq[-1 - k]["equity"] - 1
            b = tw[-1]["equity"] / tw[-1 - k]["equity"] - 1
            perf.setdefault(mid, {})["recent_excess"] = round((a - b) * 100, 2)
    return perf


def cut(px: dict, day: str) -> dict:
    out = {}
    for k, s in px.items():
        n = sum(1 for d in s["dates"] if d <= day)
        out[k] = {f: v[:n] for f, v in s.items()}
    return out


def main(argv=None, history_fn=data.history, get_json=data.get_json, now=None) -> dict:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="site/data")
    args = ap.parse_args(argv)
    out = Path(args.out)
    now = now or datetime.now(TW)
    state = _read(out / STATE_FILE) or engine.new_state()
    sym, names, chain_of = universe()

    px_all = history_fn([*sym.values(), *(b["symbol"] for b in C.BENCHMARKS), "^VIX"])
    taiex = px_all.get("^TWII")
    if not taiex:
        raise RuntimeError("抓不到台股加權指數，今天不處理")
    # Yahoo 的加權指數偶爾晚一兩天才有新 K 棒，交易日以指數、0050、台積電三者聯集為準
    cal = set(taiex["dates"])
    for k in ("0050.TW", "2330.TW"):
        cal |= set((px_all.get(k) or {}).get("dates") or [])
    dates = sorted(cal)
    today = now.date().isoformat()
    if dates and dates[-1] == today and now.hour < 14:  # 盤中的 K 棒還沒收盤
        dates = dates[:-1]
    day = dates[-1]
    px = cut(px_all, day)

    latest = _read(out / "latest.json")
    sig = latest.get("signals") or {}
    chains = {c["id"]: {"light": c.get("light"), "name": c.get("name"), "why": c.get("why")} for c in sig.get("chains") or []}
    chip_dates = dates[-5:]
    cache = state.get("chips_cache") or {}
    chips = data.fetch_chips(chip_dates, cache, get=get_json)
    state["chips_cache"] = {d: chips[d] for d in sorted(chips)[-10:]}
    vix = (px.get("^VIX") or {}).get("close") or [None]
    tw_close = taiex["close"][:len(px["^TWII"]["close"])]
    ma60 = sum(tw_close[-60:]) / 60 if len(tw_close) >= 60 else None
    ma200 = sum(tw_close[-200:]) / 200 if len(tw_close) >= 200 else None
    warnings = []
    if not chips.get(day):
        warnings.append(f"{day} 的法人買賣超還沒抓到，投信／外資方法今天維持原持股")
    ctx = {
        "date": day, "codes": list(sym), "sym": sym, "px": px, "chain_of": chain_of, "chains": chains,
        "revenue": sig.get("revenue_latest") or {}, "chips": chips, "chip_dates": [d for d in chip_dates if d in chips],
        "value": data.fetch_value(get=get_json), "ai_watch": ai_watch(state, _read(out / "ai_summary.json"), dates),
        "regime": {"light": C.BUSINESS_CYCLE.get("light"), "score": C.BUSINESS_CYCLE.get("score"),
                   "above_ma60": (tw_close[-1] >= ma60) if ma60 else None,
                   "above_ma200": (tw_close[-1] >= ma200) if ma200 else None, "ma60": round(ma60, 2) if ma60 else None,
                   "taiex": tw_close[-1], "vix": vix[-1]},
        "warnings": warnings,
        "perf_fn": lambda st: method_perf(st, px, sym, dates),
    }
    if not ctx["chip_dates"] or ctx["chip_dates"][-1] != day:
        ctx["chips"] = {}  # 決策日當天沒有法人資料就不要用舊資料選股
    if not ctx["value"]:
        warnings.append("本益比／殖利率資料抓不到，價值方法今天維持原持股")
    state = engine.run_day(state, ctx, dates, px, sym, names)
    result = summary.build(state, px, sym, names, dates, ctx, now.isoformat(timespec="minutes"))
    out.mkdir(parents=True, exist_ok=True)
    (out / STATE_FILE).write_text(json.dumps(state, ensure_ascii=False, separators=(",", ":")), "utf-8")
    (out / OUT_FILE).write_text(json.dumps(result, ensure_ascii=False, indent=1), "utf-8")
    log.info("決策日 %s，第 %d/%d 天，狀態 %s", day, len(state["days"]), C.TRADING_DAYS, state["status"])
    for m in result["methods"]:
        log.info("%-12s %+6.2f%%  持股 %d 檔  委託 買%d 賣%d", m["name"], m["return_pct"], len(m["holdings"]),
                 len((m["pending"] or {}).get("buys", [])), len((m["pending"] or {}).get("sells", [])))
    return result


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    main()
