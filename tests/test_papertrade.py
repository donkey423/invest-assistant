"""模擬帳戶：用假行情跑好幾天，檢查成交價、手續費、重跑不重複、30 天後停止。"""
import json
import math
import random
from datetime import date, datetime, timedelta, timezone

import pytest

from papertrade import __main__ as pm
from papertrade import config as C
from papertrade import engine, methods

TW = timezone(timedelta(hours=8))


_CACHE = {}


def fake_px(symbols, end: str, days=330, seed=3):
    key = (tuple(symbols), end)
    if key in _CACHE:
        return _CACHE[key]
    out = _CACHE[key] = {}
    start = date(2026, 11, 20) - timedelta(days=int(days * 1.45))
    for sym in symbols:
        rnd = random.Random(f"{seed}-{sym}")
        p, d, ds, o, c = 100.0, start, [], [], []
        while True:
            d += timedelta(days=1)
            if d.weekday() >= 5:
                continue
            if d.isoformat() > end:
                break
            op = p * math.exp(rnd.gauss(0, 0.005))
            p = op * math.exp(rnd.gauss(0.0005, 0.015))
            ds.append(d.isoformat()); o.append(round(op, 2)); c.append(round(p, 2))
        out[sym] = {"dates": ds, "open": o, "close": c}
    return out


def fake_get(url):
    if "T86" in url:
        d = url.split("date=")[1][:8]
        rnd = random.Random(d)
        codes = [s.split(".")[0] for s in pm.universe()[0].values()]
        return {"stat": "OK", "fields": ["證券代號", "證券名稱", "外陸資買賣超股數(不含外資自營商)", "投信買賣超股數"],
                "data": [[c, "x", f"{rnd.randint(-900000, 900000):,}", str(rnd.randint(-200000, 300000))] for c in codes]}
    if "BWIBBU" in url:
        codes = list(pm.universe()[0])
        return [{"Code": c, "PEratio": str(8 + i % 20), "DividendYield": str(2 + (i % 7) * 0.6), "PBratio": "1.5"}
                for i, c in enumerate(codes)]
    raise OSError("offline")


def setup_dir(tmp_path):
    sym = pm.universe()[0]
    rev = {c: {"ym": "2026-10", "yoy": (i % 9) * 7 - 15, "ytd_yoy": (i % 5) * 4, "rev": 1} for i, c in enumerate(sym)}
    chains = [{"id": ch["id"], "name": ch["name"], "light": "轉強" if i % 2 else "持平", "why": ["測試"]}
              for i, ch in enumerate(pm.bcfg.CHAINS)]
    (tmp_path / "latest.json").write_text(json.dumps({"signals": {"chains": chains, "revenue_latest": rev}}), "utf-8")
    (tmp_path / "ai_summary.json").write_text(json.dumps({"written_at": "2026-11-10T07:50+08:00", "themes": [
        {"title": "記憶體報價", "watch": ["南亞科 2408", "華邦電 2344", "美光 MU"]}]}), "utf-8")


def run(tmp_path, day, hour=18):
    now = datetime.fromisoformat(day).replace(hour=hour, tzinfo=TW)
    return pm.main(["--out", str(tmp_path)], history_fn=lambda syms: fake_px(syms, day), get_json=fake_get, now=now)


def trading_days(start, n):
    d, out = date.fromisoformat(start), []
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def test_first_day_only_places_orders(tmp_path):
    setup_dir(tmp_path)
    r = run(tmp_path, "2026-11-09")
    assert r["days_done"] == 0 and r["start"] is None
    by = {m["id"]: m for m in r["methods"]}
    assert len(by) == len(C.METHODS)
    for mid in ("momentum", "reversal", "revenue", "trust", "foreign", "value", "chain", "combo"):
        assert by[mid]["pending"]["buys"], mid
        assert all(m["equity_now"] == C.START_CASH for m in r["methods"])
    assert {b["code"] for b in by["ai_theme"]["pending"]["buys"]} == {"2408", "2344"}


def test_fill_at_next_open_with_fees(tmp_path):
    setup_dir(tmp_path)
    run(tmp_path, "2026-11-09")
    r = run(tmp_path, "2026-11-10")
    assert r["start"] == "2026-11-10" and r["days_done"] == 1
    px = fake_px(list(pm.universe()[0].values()), "2026-11-10")
    st = json.loads((tmp_path / "papertrade_state.json").read_text("utf-8"))
    acc = st["accounts"]["momentum"]
    assert len(acc["positions"]) == C.TOP_N
    for code, pos in acc["positions"].items():
        s = px[pm.universe()[0][code]]
        assert pos["price"] == s["open"][-1]  # 隔天開盤價成交
        assert pos["cost"] == pytest.approx(pos["shares"] * pos["price"] + engine.fee(pos["shares"] * pos["price"]), abs=0.01)
    assert acc["cash"] >= 0
    total = acc["cash"] + sum(p["shares"] * px[pm.universe()[0][c]]["close"][-1] for c, p in acc["positions"].items())
    assert acc["equity"][-1]["equity"] == round(total)


def test_rerun_same_day_is_idempotent(tmp_path):
    setup_dir(tmp_path)
    for d in ("2026-11-09", "2026-11-10", "2026-11-11"):
        a = run(tmp_path, d)
    b = run(tmp_path, "2026-11-11")
    assert [m["equity"] for m in a["methods"]] == [m["equity"] for m in b["methods"]]
    assert a["days_done"] == b["days_done"] == 2


def test_intraday_bar_is_ignored(tmp_path):
    setup_dir(tmp_path)
    r = run(tmp_path, "2026-11-10", hour=10)
    assert r["last_decision"] == "2026-11-09"


def test_trust_holds_11_days_and_stops_after_30(tmp_path):
    setup_dir(tmp_path)
    days = ["2026-11-09", *trading_days("2026-11-10", 32)]
    for d in days:
        r = run(tmp_path, d)
    assert r["status"] == "done" and r["days_done"] == C.TRADING_DAYS
    st = json.loads((tmp_path / "papertrade_state.json").read_text("utf-8"))
    trust = st["accounts"]["trust"]["trades"]
    first_sell = next(t for t in trust if t["side"] == "賣")
    held = [d for d in st["days"] if first_sell["held_from"] <= d < first_sell["date"]]
    assert len(held) == 11
    by = {m["id"]: m for m in r["methods"]}
    assert by["momentum"]["picks_hit"]["n"] > 0
    assert sorted(m["rank"] for m in r["methods"]) == list(range(1, len(C.METHODS) + 1))
    assert len(r["benchmarks"]["^TWII"]["equity"]) == C.TRADING_DAYS


def test_exposure_rules():
    assert methods.exposure({"light": "紅燈", "above_ma60": True, "vix": 18})[0] == 1.0
    lvl, note = methods.exposure({"light": "綠燈", "above_ma60": False, "vix": 30})
    assert lvl == pytest.approx(0.4) and "跌破季線" in note


def test_lagging_index_does_not_delay_decision(tmp_path):
    setup_dir(tmp_path)
    now = datetime.fromisoformat("2026-11-09").replace(hour=18, tzinfo=TW)

    def lagging(syms):
        px = fake_px(syms, "2026-11-09")
        px["^TWII"] = {k: v[:-1] for k, v in px["^TWII"].items()}  # 指數少最後一天
        return px
    r = pm.main(["--out", str(tmp_path)], history_fn=lagging, get_json=fake_get, now=now)
    assert r["last_decision"] == "2026-11-09"
