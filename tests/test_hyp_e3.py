"""假設 E3：combo 的持股比例刪除 VIX 項、改乘大盤自身已實現波動的係數；E3ctl＝只刪除 VIX 項。全部用合成資料。"""
import copy
from statistics import median, stdev

import pytest

from papertrade import backtest as bt
from papertrade import config as C
from papertrade import engine, methods
from papertrade.research import dataset, report, request, runner
from tests.test_research import UNI, make

E3, CTL = {"drop_vix": True, "realized_vol": True}, {"drop_vix": True}


def _brute(closes: list[float]) -> float | None:
    """照定義從頭算：只給到決策日為止的收盤價。"""
    rets = [b / a - 1 for a, b in zip(closes, closes[1:])]
    sigmas = [stdev(rets[j - 20:j + 1]) for j in range(20, len(rets))]   # 每一天的 σ_21
    if len(sigmas) < 252:
        return None
    return min(1.0, median(sigmas) / sigmas[-1])


def _tw(d: dict, n: int, lookback=None) -> dict:
    tw = d["px"]["^TWII"]
    a = max(0, n - lookback) if lookback else 0
    return {"dates": tw["dates"][a:n], "close": tw["close"][a:n]}


# ---------- 波動係數 ----------

def test_expanding_median_equals_brute_force_with_truncated_windows():
    d = make()
    closes = d["px"]["^TWII"]["close"]
    memo, memo_full, got = {}, {}, []
    for n in range(260, len(closes) + 1):   # 研究框架第一次決策在第 260 根，之後每天只給最後 320 根
        x = methods.realized_vol_scale(_tw(d, n, runner.LOOKBACK), memo)
        assert x == methods.realized_vol_scale(_tw(d, n), memo_full)             # 給全部歷史也一樣
        assert x == methods.realized_vol_scale(_tw(d, n, runner.LOOKBACK), memo)   # 同一天重複呼叫不會重複累積
        want = _brute(closes[:n])
        assert (x is None) == (want is None) and (x is None or x == pytest.approx(want, rel=1e-12))
        got.append(x)
    # 暖機：要有 252 個 σ_21。第 1 個 σ_21 在第 22 根 K 棒（21 筆報酬），所以第 273 根起才啟用
    k = 273 - 260
    assert got[:k] == [None] * k and all(x is not None for x in got[k:])
    assert any(x < 1 for x in got[k:]) and any(x == 1.0 for x in got[k:]) and all(0 < x <= 1 for x in got[k:])


def test_scale_uses_nothing_after_decision_day():
    d = make()
    n = 330
    a = methods.realized_vol_scale(_tw(d, n), {})
    crash = copy.deepcopy(d)
    for i in range(n, len(crash["px"]["^TWII"]["close"])):
        crash["px"]["^TWII"]["close"][i] *= 0.5 if i % 2 else 1.5   # 之後的資料亂改
    assert a == methods.realized_vol_scale(_tw(crash, n), {}) == pytest.approx(_brute(d["px"]["^TWII"]["close"][:n]))
    assert methods.realized_vol_scale(None, {}) is None and methods.realized_vol_scale({"dates": [], "close": []}, {}) is None
    flat = {"dates": d["px"]["^TWII"]["dates"][:300], "close": [100.0] * 300}
    assert methods.realized_vol_scale(flat, {}) is None   # 波動為 0：不縮放


# ---------- 持股比例 ----------

@pytest.mark.parametrize("above60", [True, False, None])
@pytest.mark.parametrize("vix", [None, 18.0, 30.0])
@pytest.mark.parametrize("scale", [None, 1.0, 0.8, 0.2])
def test_exposure_with_and_without_flags(above60, vix, scale):
    regime = {"light": "紅燈", "above_ma60": above60, "vix": vix, "vol_scale": scale}
    plain = {k: v for k, v in regime.items() if k != "vol_scale"}
    trend = 1.0 - (0.3 if above60 is False else 0)
    base = max(0.3, trend - (0.2 if vix and vix >= 25 else 0))
    # 沒帶旗標：和原本的規則完全相同（多出來的鍵不影響）
    assert methods.exposure(regime) == methods.exposure(plain) == methods.exposure(regime, {}) == methods.exposure(regime, {"other": 1})
    assert methods.exposure(regime)[0] == pytest.approx(base)
    level, note = methods.exposure(regime, CTL)   # 對照組：只刪除 VIX 項
    assert level == pytest.approx(max(0.3, trend)) and "VIX" not in note and "波動" not in note
    level, note = methods.exposure(regime, E3)    # E3：刪除 VIX 項，再乘係數；上限 1、下限 0.3
    assert level == pytest.approx(max(0.3, trend * (scale if scale is not None else 1.0))) and "VIX" not in note
    assert ("波動" in note) == (scale is not None and scale < 1)


def test_decide_changes_combo_only(monkeypatch):
    """旗標開著：只有 combo 的持股比例改變；Claude 判斷、Claude 判斷 v2 仍然照原本的規則（含 VIX 項）。"""
    seen = {}
    monkeypatch.setattr(engine, "plan_orders", lambda state, mid, acc, ranking, day, px, sym, expo=1.0: (
        seen.__setitem__(mid, expo), {"decided": day, "sells": [], "buys": []})[1])
    monkeypatch.setattr(engine, "realized_vol_scale", lambda tw, memo: 0.8)
    for mid in list(methods.METHOD_FNS):
        monkeypatch.setitem(methods.METHOD_FNS, mid, lambda ctx: [])

    def decide(flags):
        seen.clear()
        state = engine.new_state()
        ctx = {"regime": {"light": "紅燈", "above_ma60": False, "vix": 30.0}, **({"variant": flags} if flags is not None else {})}
        engine.decide(state, ctx, "2026-03-02", {}, {}, {})
        return dict(seen), {j["method"]: j["note"] for j in state["journal"]}, ctx

    for flags in (None, {}, {"drop_vix": False, "realized_vol": False}):
        e, notes, ctx = decide(flags)
        assert e["combo"] == e["claude"] == e["claude2"] == pytest.approx(0.5) and "VIX" in notes["combo"]
        assert "vol_scale" not in ctx["regime"] and "memo" not in ctx   # 沒帶旗標連算都不會算
    e, notes, _ = decide(CTL)
    assert e["combo"] == pytest.approx(0.7) and e["claude"] == e["claude2"] == pytest.approx(0.5)
    assert "VIX" not in notes["combo"] and "VIX" in notes["claude"] and "VIX" in notes["claude2"]
    e, notes, ctx = decide(E3)
    assert e["combo"] == pytest.approx(0.7 * 0.8) and e["claude"] == e["claude2"] == pytest.approx(0.5)
    assert "波動" in notes["combo"] and "波動" not in notes["claude"] and ctx["regime"]["vol_scale"] == 0.8
    assert all(v == 1.0 for mid, v in e.items() if mid not in ("combo", "claude", "claude2"))


# ---------- 整段跑 ----------

@pytest.fixture(scope="module")
def data():
    """合成資料的 VIX 很少超過 25，這裡在樣本內硬塞一段 VIX 30，對照組才看得出差別。"""
    full = make()
    b = dataset.boundary(bt.calendar(full["px"]))
    ins, _ = dataset.split_dataset(full, b["holdout_start"])
    vix = ins["px"]["^VIX"]
    for i in range(280, 330):
        vix["close"][i] = 30.0
    return b, ins


@pytest.fixture(scope="module")
def runs(data):
    b, ins = data
    man = {**b, "insample_sha256": "x" * 64}
    return [runner.run_variant(name, ins, man, uni=UNI) for name in ("baseline", "E3", "E3ctl")]


def test_variants_registered_and_request_file_valid():
    assert runner.VARIANTS["E3"] == E3 and runner.VARIANTS["E3ctl"] == CTL   # 對照組＝E3 拿掉波動係數，其餘相同
    assert "lookback" not in runner.VARIANTS["E3"]                           # 用 ctx["memo"] 累積，不需要拉長每天的視窗
    assert request.load_request("research/requests/103-e3.json") == [
        ["run", "--variant", "baseline", "--variant", "E3", "--variant", "E3ctl"],
        ["compare", "--base", "baseline", "--variant", "E3", "--variant", "E3ctl"]]


def test_research_runs_change_only_combo(runs):
    base, e3, ctl = runs
    assert base["regime"]["all"]["vix25"] >= 40
    for res in (e3, ctl):
        for mid in runner.METHOD_IDS:
            same = res["methods"][mid]["equity"] == base["methods"][mid]["equity"] and res["methods"][mid]["trades"] == base["methods"][mid]["trades"]
            assert same == (mid != "combo"), (res["variant"], mid)
    assert e3["methods"]["combo"]["equity"] != ctl["methods"]["combo"]["equity"]
    assert len({r["hash"] for r in runs}) == 3


def test_vol_scale_diagnostic(runs):
    base, e3, ctl = runs
    assert "vol_scale" not in base["regime"] and "vol_scale" not in ctl["regime"]
    k = e3["regime"]["vol_scale"]
    assert k["all"]["warmup_days"] == 12 and 0 < k["all"]["scaled_days"] < len(e3["dates"]) and 0 < k["all"]["min"] < k["all"]["mean"] < 1
    assert sum(f["warmup_days"] for f in k["folds"]) == 12 and sum(f["scaled_days"] for f in k["folds"]) == k["all"]["scaled_days"]
    md = report.result_markdown(e3)
    assert "假設 E3 的診斷" in md and "假設 E3 的診斷" not in report.result_markdown(base)
    cmp = report.compare(base, e3, [], n_boot=50)
    assert cmp["methods"]["combo"]["affected"] and not cmp["methods"]["graham"]["affected"]
    report.compare_markdown(cmp)


def test_combo_exposure_in_run_matches_brute_force(data, monkeypatch):
    """整段跑的時候，combo 每天拿到的持股比例＝只用當天以前的大盤資料、照定義從頭算出來的值（沒有偷看、memo 沒有累積錯）。"""
    b, ins = data
    seen = {}
    real = engine.plan_orders

    def plan(state, mid, acc, ranking, day, px, sym, expo=1.0):
        if mid == "combo":
            seen[day] = expo
        return real(state, mid, acc, ranking, day, px, sym, expo)
    monkeypatch.setattr(engine, "plan_orders", plan)
    tw = ins["px"]["^TWII"]

    def want(day, with_vol):
        n = tw["dates"].index(day) + 1
        c = tw["close"][:n]
        level = 1.0 - 0.3 * (c[-1] < sum(c[-60:]) / 60)
        scale = _brute(c) if with_vol else None
        return max(0.3, level * (scale if scale is not None else 1.0))

    for flags, with_vol in ((E3, True), (CTL, False)):
        seen.clear()
        runner.simulate(ins, flags, b["warmup_end"], uni=UNI)
        assert len(seen) > 100 and len(set(seen.values())) > (2 if with_vol else 1)
        for day, expo in seen.items():
            assert expo == pytest.approx(want(day, with_vol), rel=1e-12), day
    seen.clear()
    runner.simulate(ins, {}, b["warmup_end"], uni=UNI)   # baseline：VIX 項還在
    assert any(expo == pytest.approx(want(day, False) - 0.2) for day, expo in seen.items())


def _run_all(ds, flags, start, uni, n_days=128):
    """整套方法（含 Claude 判斷、Claude 判斷 v2；研究框架平常不含它們）帶著旗標逐日跑，回傳 state。

    刻意不給 perf_fn：Claude 判斷會依「其他帳戶最近的績效」調整投票權重，combo 帳戶一變它就會跟著變，
    那是方法本身的設計、不是共用程式被改到。拿掉這條回饋，才能單獨證明共用程式沒有動到 Claude 判斷。
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


def test_claude_accounts_unaffected(data):
    b, ins = data
    off = _run_all(ins, None, b["warmup_end"], UNI)
    for flags in (E3, CTL):
        on = _run_all(ins, flags, b["warmup_end"], UNI)
        assert {"claude", "claude2", "combo"} <= set(on["accounts"])
        for mid, acc in on["accounts"].items():
            assert (acc == off["accounts"][mid]) == (mid != "combo"), mid
    assert any("降低持股比例" in t["reason"] for t in off["accounts"]["claude"]["trades"])   # Claude 判斷的持股比例真的有在動
