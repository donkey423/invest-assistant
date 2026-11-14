"""假設 S2：oneil、tech4 的停損門檻由固定 -8% 改為 −5 × 進場決策日前 60 筆日報酬的標準差（進場時固定）。全部用合成資料。"""
import copy
import json
import random
from statistics import median, stdev

import pytest

from papertrade import backtest as bt
from papertrade import config as C
from papertrade import engine
from papertrade.research import dataset, report, request, runner, synthetic
from tests.test_research import UNI, make

FLAGS = {"vol_scaled_stop": True}
SYM = {"A": "A.TW", "B": "B.TW"}


def _series(n, vol, seed=0, start=100.0):
    rnd, p, c = random.Random(seed), start, []
    for _ in range(n):
        p *= 1 + rnd.gauss(0, vol)
        c.append(round(p, 2))
    return {"dates": synthetic.weekdays("2025-01-02", n), "open": list(c), "close": c, "volume": [1e6] * n}


def _brute(closes):
    """照定義：最後 60 筆收盤對收盤報酬的樣本標準差 × −5（%）。"""
    rets = [b / a - 1 for a, b in zip(closes, closes[1:])]
    return -5 * stdev(rets[-60:]) * 100 if len(rets) >= 60 else None


# ---------- 門檻 ----------

def test_vol_stop_matches_definition_and_ignores_later_data():
    s = _series(120, 0.02)
    for n in (61, 80, 120):
        day = s["dates"][n - 1]
        assert engine.vol_stop(s, day) == pytest.approx(_brute(s["close"][:n]), rel=1e-12)   # 給了之後的資料也只用到 day
        cut = {k: v[:n] for k, v in s.items()}
        assert engine.vol_stop(cut, day) == engine.vol_stop(s, day)
    later = copy.deepcopy(s)
    later["close"][100:] = [1.0] * 20
    assert engine.vol_stop(later, s["dates"][99]) == engine.vol_stop(s, s["dates"][99])
    assert engine.vol_stop(s, s["dates"][99]) != engine.vol_stop(s, s["dates"][100])
    # 不足 60 筆報酬（61 根收盤）、標準差為 0、沒有資料：None（退回固定門檻）
    assert engine.vol_stop(s, s["dates"][59]) is None and engine.vol_stop(s, s["dates"][60]) is not None
    flat = {**s, "close": [100.0] * 120}
    assert engine.vol_stop(flat, s["dates"][-1]) is None and engine.vol_stop(None, "2025-06-01") is None
    assert engine.vol_stop(_series(120, 0.01), s["dates"][-1]) > -8 > engine.vol_stop(_series(120, 0.03), s["dates"][-1])
    assert (engine.STOP_VOL_WINDOW, engine.STOP_VOL_MULT, engine.STOP_VARIANT_METHODS) == (60, 5, ("oneil", "tech4"))


def _state(flags):
    state = engine.new_state()
    state["days"] = ["2025-01-02"]
    if flags is not None:
        state["variant"] = flags
    return state


def _buy_plan(mid, flags, px, day):
    state = _state(flags)
    acc = state["accounts"].setdefault(mid, engine.new_account())
    ranking = [{"code": c, "score": 1.0, "reason": "測試", "votes": 3} for c in ("A", "B")]
    return engine.plan_orders(state, mid, acc, ranking, day, px, SYM), acc


@pytest.mark.parametrize("mid", ["oneil", "tech4"])
def test_threshold_is_fixed_at_entry_decision_day(mid):
    a, b = _series(120, 0.025, 1), _series(120, 0.01, 2)
    b = {k: v[80:] for k, v in b.items()}   # B 只有 40 根：不足 60 筆報酬
    px = {"A.TW": {k: v[:100] for k, v in a.items()}, "B.TW": {k: v[:20] for k, v in b.items()}}
    day, nxt = a["dates"][99], a["dates"][100]
    plan, acc = _buy_plan(mid, FLAGS, px, day)
    want = round(_brute(a["close"][:100]), 4)
    assert [(x["code"], x["stop"], x.get("stop_fallback")) for x in plan["buys"]] == [("A", want, None), ("B", -8, True)]
    off, _ = _buy_plan(mid, None, px, day)
    assert [{k: v for k, v in x.items() if k not in ("stop", "stop_fallback")} for x in plan["buys"]] == off["buys"]
    assert all("stop" not in x for x in off["buys"])
    # 隔天成交：門檻存在持股與買進紀錄上，之後股價怎麼走都不會再變
    px2 = {"A.TW": {k: v[:101] for k, v in a.items()}, "B.TW": {k: v[:21] for k, v in b.items()}}
    acc["pending"] = plan
    engine._fill(acc, nxt, px2, SYM, {})
    assert acc["positions"]["A"]["stop"] == want == acc["trades"][0]["stop"] and "stop_fallback" not in acc["positions"]["A"]
    assert acc["positions"]["B"]["stop"] == -8 and acc["positions"]["B"]["stop_fallback"] is True and acc["trades"][1]["stop_fallback"] is True


def _held_plan(mid, flags, chg_pct, stop=None, held_days=1):
    """進場價 100 的持股、今天漲跌 chg_pct%；stop＝持股上記的門檻。"""
    state = _state(flags)
    state["days"] = synthetic.weekdays("2025-01-02", held_days)
    acc = state["accounts"].setdefault(mid, engine.new_account())
    pos = {"shares": 1000, "price": 100.0, "cost": 100_142.5, "date": "2025-01-02", "reason": "測試"}
    if stop is not None:
        pos["stop"] = stop
    acc["positions"]["A"] = pos
    day = state["days"][-1]
    px = {"A.TW": {"dates": [day], "open": [100.0], "close": [100.0 + chg_pct], "volume": [1e6]}}
    ranking = [{"code": "A", "score": 1.0, "reason": "測試", "votes": 3}]
    return engine.plan_orders(state, mid, acc, ranking, day, px, SYM)["sells"], state


@pytest.mark.parametrize("mid", ["oneil", "tech4"])
def test_stop_uses_the_stored_threshold(mid):
    # 高波動股（門檻 -12.5%）：跌 9% 不停損（固定門檻會），記一筆診斷；跌 13% 才停損
    sells, state = _held_plan(mid, FLAGS, -9.0, stop=-12.5)
    assert sells == [] and state["stop_diag"] == [{"method": mid, "date": "2025-01-02", "code": "A", "entry": "2025-01-02",
                                                   "chg": pytest.approx(-9.0), "stop": -12.5}]
    sells, state = _held_plan(mid, FLAGS, -13.0, stop=-12.5)
    assert sells == [{"code": "A", "reason": "跌 -13.0%，觸發 -12.5% 停損（5 倍日標準差）"}] and "stop_diag" not in state
    # 低波動股（門檻 -5%）：跌 6% 就停損（固定門檻不會）
    sells, state = _held_plan(mid, FLAGS, -6.0, stop=-5.0)
    assert len(sells) == 1 and "停損" in sells[0]["reason"] and "stop_diag" not in state
    assert _held_plan(mid, FLAGS, -4.0, stop=-5.0)[0] == []
    # 持股上沒有門檻（旗標開啟前就抱著的）：照固定 -8%
    assert _held_plan(mid, FLAGS, -9.0)[0] == _held_plan(mid, None, -9.0)[0] == [{"code": "A", "reason": "跌 -9.0%，觸發 -8% 停損"}]
    # 沒被停損時，持有天數出場照舊（tech4 的停利也照舊）
    sells, _ = _held_plan(mid, FLAGS, -9.0, stop=-12.5, held_days=20)
    assert sells == [{"code": "A", "reason": "已持有 20 個交易日，依方法出場"}]
    if mid == "tech4":
        assert "停利" in _held_plan(mid, FLAGS, 10.5, stop=-12.5)[0][0]["reason"]


@pytest.mark.parametrize("flags", [None, {}, {"vol_scaled_stop": False}, {"other": True}])
@pytest.mark.parametrize("mid", ["oneil", "tech4", "claude", "claude2"])
def test_flag_off_is_the_original_rule(mid, flags):
    limit = next(m for m in C.METHODS if m["id"] == mid)["stop_loss"]
    for chg, stop in ((-11.0, -12.5), (-11.0, None), (-6.0, -5.0), (10.5, -12.5)):   # 就算持股上有門檻，沒旗標也不看
        sells, state = _held_plan(mid, flags, chg, stop=stop)
        want = ([{"code": "A", "reason": f"跌 {chg:.1f}%，觸發 {limit}% 停損"}] if chg <= limit else
                [{"code": "A", "reason": "漲 +10.5%，觸發 +10% 停利"}] if mid == "tech4" and chg >= 10 else [])
        assert sells == want and "stop_diag" not in state
    px = {"A.TW": _series(120, 0.025, 1), "B.TW": _series(120, 0.01, 2)}
    plan, _ = _buy_plan(mid, flags, px, px["A.TW"]["dates"][-1])
    assert plan["buys"] and all("stop" not in b for b in plan["buys"])


@pytest.mark.parametrize("mid", ["claude", "claude2"])
def test_claude_accounts_ignore_the_flag(mid):
    """旗標開著，Claude 判斷（共用同一段停損程式）仍然用自己的固定門檻，買進委託也不帶門檻。"""
    for chg, stop in ((-11.0, -12.5), (-9.0, -12.5), (-6.0, -5.0), (-11.0, None)):
        on, state = _held_plan(mid, FLAGS, chg, stop=stop)
        assert on == _held_plan(mid, None, chg, stop=stop)[0] and "stop_diag" not in state
    assert len(_held_plan(mid, FLAGS, -11.0, stop=-12.5)[0]) == 1
    px = {"A.TW": _series(120, 0.025, 1), "B.TW": _series(120, 0.01, 2)}
    day = px["A.TW"]["dates"][-1]
    assert _buy_plan(mid, FLAGS, px, day)[0] == _buy_plan(mid, None, px, day)[0]


def test_injected_method_with_stop_loss_is_unaffected(monkeypatch):
    """任何不在目標清單裡、但也有 stop_loss 的方法（這裡臨時塞一個）都不受旗標影響。"""
    monkeypatch.setattr(C, "METHODS", [*C.METHODS, {"id": "probe", "name": "測試", "stop_loss": -8, "max_hold": 20}])
    sells, state = _held_plan("probe", FLAGS, -9.0, stop=-12.5)
    assert sells == [{"code": "A", "reason": "跌 -9.0%，觸發 -8% 停損"}] and "stop_diag" not in state
    px = {"A.TW": _series(120, 0.025, 1), "B.TW": _series(120, 0.01, 2)}
    assert all("stop" not in b for b in _buy_plan("probe", FLAGS, px, px["A.TW"]["dates"][-1])[0]["buys"])


# ---------- 診斷的「之後報酬」 ----------

def test_spared_stops_after_return():
    px = {"A.TW": {"dates": ["d1", "d2", "d3", "d4", "d5"], "open": [100.0, 90.0, 92.0, 95.0, 99.0], "close": [91.0, 91.0, 93.0, 96.0, 98.0],
                   "div": [0.0, 1.0, 0.0, 2.0, 0.0]}}
    ev = {"method": "oneil", "date": "d1", "code": "A", "entry": "d0", "chg": -9.0, "stop": -12.5, "symbol": "A.TW"}
    sell = {"date": "d4", "side": "賣", "code": "A", "price": 95.0, "held_from": "d0", "reason": "已持有 20 個交易日，依方法出場"}
    other = {"date": "d3", "side": "賣", "code": "A", "price": 1.0, "held_from": "dX", "reason": "別筆持股"}
    got = runner.spared_stops([ev, {**ev, "date": "d2"}], [other, sell], px, "d1", "d5")   # 同一筆持股只算第一天
    # 固定門檻 d2 開盤 90 出場；實際 d4 開盤 95 出場，中間 d4 除息 2 元（d2 當天除息的兩邊都領得到，不算）
    assert got["count"] == 1 and got["events"][0]["after_return"] == pytest.approx(97.0 / 90.0 - 1) == got["mean_after_return"]
    assert got["events"][0]["exit_date"] == "d4" and got["events"][0]["stop"] == -12.5
    still = runner.spared_stops([ev], [], px, "d1", "d5")["events"][0]
    assert still["after_return"] == pytest.approx(100.0 / 90.0 - 1) and still["exit_reason"] == "期末仍持有"
    cut = runner.spared_stops([ev], [sell], px, "d1", "d3")["events"][0]   # 只用到 end 為止的資料
    assert cut["after_return"] == pytest.approx(93.0 / 90.0 - 1) and cut["exit_date"] is None
    assert runner.spared_stops([ev], [sell], px, "d2", "d5") == {"count": 0, "mean_after_return": None, "events": []}
    last = runner.spared_stops([{**ev, "date": "d5"}], [], px, "d1", "d5")
    assert last["count"] == 1 and last["events"][0]["after_return"] is None and last["mean_after_return"] is None


# ---------- 整段跑 ----------

@pytest.fixture(scope="module")
def data():
    full = make()
    b = dataset.boundary(bt.calendar(full["px"]))
    ins, _ = dataset.split_dataset(full, b["holdout_start"])
    return b, ins


@pytest.fixture(scope="module")
def runs(data):
    b, ins = data
    man = {**b, "insample_sha256": "x" * 64}
    return runner.run_variant("baseline", ins, man, uni=UNI), runner.run_variant("S2", ins, man, uni=UNI)


def test_variant_registered_and_request_file_valid():
    assert runner.VARIANTS["S2"] == FLAGS
    assert request.load_request("research/requests/105-s2.json") == [
        ["run", "--variant", "baseline", "--variant", "S2"], ["compare", "--base", "baseline", "--variant", "S2"]]


def test_research_run_changes_only_target_methods(runs):
    base, s2 = runs
    for m in runner.METHOD_IDS:
        same = s2["methods"][m]["equity"] == base["methods"][m]["equity"] and s2["methods"][m]["trades"] == base["methods"][m]["trades"]
        assert same == (m not in ("oneil", "tech4")), m
    assert not any("stop" in t for m in base["methods"].values() for t in m["trades"])
    assert all("vol_stop" not in m for m in base["methods"].values())
    assert {m for m, v in s2["methods"].items() if "vol_stop" in v} == {"oneil", "tech4"}


def test_thresholds_in_run_use_only_data_up_to_decision_day(runs, data):
    base, s2 = runs
    b, ins = data
    cal = bt.calendar(ins["px"])
    n = 0
    for mid in ("oneil", "tech4"):
        buys = [t for t in s2["methods"][mid]["trades"] if t["side"] == "買"]
        assert buys and all("stop" in t for t in buys)
        for t in buys:
            decided = cal[cal.index(t["date"]) - 1]   # 進場決策日＝成交日的前一個交易日
            s = ins["px"][UNI[0][t["code"]]]
            want = _brute(s["close"][:s["dates"].index(decided) + 1])
            assert t["stop"] == pytest.approx(want, abs=1e-4) and not t.get("stop_fallback")
            n += 1
        # 每一筆停損出場都是跌破自己進場時的門檻
        stop_of = {(t["code"], t["date"]): t["stop"] for t in buys}
        for t in s2["methods"][mid]["trades"]:
            if t["side"] == "賣" and "停損" in t["reason"]:
                assert f"觸發 {stop_of[(t['code'], t['held_from'])]:.1f}% 停損（5 倍日標準差）" in t["reason"]
    assert n > 10


def test_diagnostics(runs):
    base, s2 = runs
    total = 0
    for mid in ("oneil", "tech4"):
        m, d = s2["methods"][mid], s2["methods"][mid]["vol_stop"]
        stops = [t["stop"] for t in m["trades"] if t["side"] == "買"]
        assert d["stop_exits"] == m["all"]["stop_exits"] == sum(1 for t in m["trades"] if t["side"] == "賣" and "停損" in t["reason"])
        assert d["thresholds"] == {"n": len(stops), "fallback": 0, "min": min(stops), "median": median(stops), "max": max(stops)}
        assert d["thresholds"]["min"] <= d["thresholds"]["median"] <= d["thresholds"]["max"] < 0
        sp = d["spared"]
        assert sp["count"] == len(sp["events"])
        for ev in sp["events"]:
            assert ev["stop"] < ev["chg"] <= -8 and ev["after_return"] is not None
            later = [t for t in m["trades"] if t["side"] == "賣" and t["code"] == ev["code"] and t["held_from"] == ev["entry"]]
            assert ev["exit_date"] == (later[0]["date"] if later else None)
        total += sp["count"]
        assert f"固定 -8% 會停損、新門檻不停損的事件 {sp['count']} 筆" in report.result_markdown(s2)
    assert total >= 1   # 合成資料裡真的有被改判的部位
    assert "波動停損（假設 S2）" not in report.result_markdown(base)
    slim = json.loads(json.dumps(report.copy_slim(s2)))
    assert slim["methods"]["oneil"]["vol_stop"] == json.loads(json.dumps(s2["methods"]["oneil"]["vol_stop"]))
    assert any("stop" in t for t in slim["methods"]["tech4"]["trades"])
    cmp = report.compare(base, s2, [], n_boot=50)
    assert cmp["methods"]["tech4"]["affected"] and not cmp["methods"]["combo"]["affected"]


def _run_all(ds, flags, start, uni, n_days=128):
    """整套方法（含 Claude 判斷、Claude 判斷 v2；研究框架平常不含它們）帶著旗標逐日跑，回傳 state。

    刻意不給 perf_fn：Claude 判斷會依「其他帳戶最近的績效」調整投票權重，oneil／tech4 帳戶一變它就會跟著變，
    那是方法本身的設計、不是共用程式被改到。拿掉這條回饋，才能單獨證明共用的停損程式沒有動到 Claude 判斷。
    """
    sym, names, chain_of = uni
    cal = bt.calendar(ds["px"])
    i0 = cal.index(start)
    tables = runner.revenue_tables(ds["rev"])
    keep_methods, keep_days = C.METHODS, C.TRADING_DAYS
    C.METHODS, C.TRADING_DAYS = [m for m in keep_methods if m["id"] != "ai_theme"], 10 ** 9
    try:
        state, memo = engine.new_state(), {}
        if flags is not None:
            state["variant"] = flags
        for i in range(i0, min(len(cal), i0 + n_days)):
            day, dates = cal[i], cal[:i + 1]
            px = runner.window_px(ds["px"], day)
            rev = {c: r for c in sym if (r := runner.revenue_at(tables, c, day))}
            val = {c: v for c in sym if (v := runner.value_at(ds["val"].get(c), day))}
            ctx = bt.day_ctx(ds, sym, chain_of, dates, px, rev=rev, val=val)
            if flags is not None:
                ctx["variant"], ctx["memo"] = flags, memo
            state = engine.run_day(state, ctx, dates, px, sym, names)
            state["checkpoint"] = None
    finally:
        C.METHODS, C.TRADING_DAYS = keep_methods, keep_days
    return state


def test_claude_accounts_unaffected_in_full_run(data):
    b, ins = data
    off, on = _run_all(ins, None, b["warmup_end"], UNI), _run_all(ins, FLAGS, b["warmup_end"], UNI)
    assert {"claude", "claude2"} <= set(on["accounts"])
    for m, acc in on["accounts"].items():
        assert (acc == off["accounts"][m]) == (m not in ("oneil", "tech4")), m
    assert not any("stop" in x for m, acc in on["accounts"].items() if m not in ("oneil", "tech4")
                   for x in [*acc["trades"], *acc["positions"].values()])
    assert any("停損" in t.get("reason", "") for m in ("claude", "claude2") for t in off["accounts"][m]["trades"])   # 它們真的有停損
