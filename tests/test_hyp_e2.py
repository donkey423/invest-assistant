"""假設 E2：combo 的趨勢訊號由「每日看 60 日線」改成「上月底看 200 日線」。全部用合成資料。"""
import copy

import pytest

from papertrade import backtest as bt
from papertrade import config as C
from papertrade import engine, methods
from papertrade.research import dataset, report, request, runner, synthetic
from tests.test_research import UNI, make

FLAGS = {"monthly_ma200": True}


def _tw(closes, start="2018-01-02"):
    return {"dates": synthetic.weekdays(start, len(closes)), "close": list(closes)}


def _brute(tw, day, n=200):
    """直接照定義算：日期在 day 所屬月份之前的最後一根，和它（含）往前 n 根的平均比。"""
    prev = [i for i, d in enumerate(tw["dates"]) if d[:7] < day[:7]]
    if not prev or prev[-1] < n - 1:
        return None
    i = prev[-1]
    return tw["close"][i] >= sum(tw["close"][i - n + 1:i + 1]) / n


# ---------- 訊號 ----------

def test_month_end_trend_matches_definition_and_is_constant_within_month():
    d = make()
    tw = d["px"]["^TWII"]
    seen = set()
    for i in range(0, len(tw["dates"])):
        day = tw["dates"][i]
        cut = {"dates": tw["dates"][:i + 1], "close": tw["close"][:i + 1]}
        got = methods.month_end_trend(cut, day)
        assert got == _brute(cut, day) == methods.month_end_trend(tw, day)   # 給不給之後的資料，結果都一樣
        seen.add(got)
    assert seen == {None, True, False}
    by_month = {}
    for day in tw["dates"]:
        by_month.setdefault(day[:7], set()).add(methods.month_end_trend(tw, day))
    assert all(len(v) == 1 for v in by_month.values())   # 同一個月只有一個值


def test_month_end_trend_ignores_everything_after_previous_month_end():
    tw = _tw([100.0 + i * 0.1 for i in range(260)])
    day = tw["dates"][-1]
    assert methods.month_end_trend(tw, day) is True
    crash = copy.deepcopy(tw)
    for i, d in enumerate(crash["dates"]):
        if d[:7] == day[:7]:
            crash["close"][i] = 1.0   # 本月崩盤：訊號要到下個月才會變
    assert methods.month_end_trend(crash, day) is True
    nxt = {"dates": [*crash["dates"], "2099-01-02"], "close": [*crash["close"], 1.0]}
    assert methods.month_end_trend(nxt, "2099-01-02") is False
    # 決策日是月底最後一個交易日時，用的仍是「上個月」的月底，不是當天
    ends = [d for d, e in zip(tw["dates"], tw["dates"][1:]) if d[:7] != e[:7]]
    last_end = ends[-1]
    low = copy.deepcopy(tw)
    low["close"][low["dates"].index(last_end)] = 1.0
    assert methods.month_end_trend(low, last_end) is True
    assert methods.month_end_trend(low, low["dates"][low["dates"].index(last_end) + 1]) is False


def test_month_end_trend_needs_200_bars_before_month_end():
    tw = _tw([100.0] * 230)
    got = [methods.month_end_trend(tw, d) for d in tw["dates"]]
    assert got == [_brute(tw, d) for d in tw["dates"]] and set(got) == {None, True}
    first = got.index(True)   # 第一個有訊號的日子：某個月的第一個交易日，而且上個月底已經是第 200 根以後
    assert tw["dates"][first][:7] != tw["dates"][first - 1][:7] and first - 1 >= 199
    assert tw["dates"][199][:7] == tw["dates"][first - 1][:7] or first - 1 == 199   # 不會更晚才開始
    assert methods.month_end_trend(None, "2020-01-02") is None and methods.month_end_trend({"dates": [], "close": []}, "2020-01-02") is None


# ---------- 持股比例 ----------

@pytest.mark.parametrize("above60", [True, False, None])
@pytest.mark.parametrize("above200m", [True, False, None])
@pytest.mark.parametrize("vix", [None, 18.0, 30.0])
def test_exposure_with_and_without_flag(above60, above200m, vix):
    regime = {"light": "紅燈", "above_ma60": above60, "above_ma200": True, "above_ma200_month_end": above200m, "vix": vix}
    plain = {k: v for k, v in regime.items() if k != "above_ma200_month_end"}
    base = 1.0 - (0.3 if above60 is False else 0) - (0.2 if vix and vix >= 25 else 0)
    new = 1.0 - (0.3 if above200m is False else 0) - (0.2 if vix and vix >= 25 else 0)
    # 沒帶旗標：多出來的鍵不影響結果，和原本的規則完全相同
    assert methods.exposure(regime) == methods.exposure(plain) == methods.exposure(regime, {}) == methods.exposure(regime, {"other": 1})
    assert methods.exposure(regime)[0] == pytest.approx(max(0.3, base))
    level, note = methods.exposure(regime, FLAGS)
    assert level == pytest.approx(max(0.3, new))   # 減碼幅度 0.3、VIX 項、上下限都不變
    assert ("上月底大盤低於年線" in note) == (above200m is False) and "跌破季線" not in note


def test_decide_gives_new_signal_to_combo_only(monkeypatch):
    """旗標開著：combo 用月底年線，Claude 判斷、Claude 判斷 v2 仍然用每日季線。"""
    seen = {}
    monkeypatch.setattr(engine, "plan_orders", lambda state, mid, acc, ranking, day, px, sym, expo=1.0: (
        seen.__setitem__(mid, expo), {"decided": day, "sells": [], "buys": []})[1])
    for mid in list(methods.METHOD_FNS):
        monkeypatch.setitem(methods.METHOD_FNS, mid, lambda ctx: [])

    def decide(regime, flags):
        seen.clear()
        state = engine.new_state()
        ctx = {"regime": regime, **({"variant": flags} if flags is not None else {})}
        engine.decide(state, ctx, "2026-03-02", {}, {}, {})
        notes = {j["method"]: j["note"] for j in state["journal"]}
        return dict(seen), notes

    regime = {"light": "紅燈", "above_ma60": False, "above_ma200_month_end": True, "vix": 18.0}
    for flags in (None, {}, {"monthly_ma200": False}):
        e, notes = decide(regime, flags)
        assert e["combo"] == e["claude"] == e["claude2"] == pytest.approx(0.7) and "跌破季線" in notes["combo"]
    e, notes = decide(regime, FLAGS)
    assert e["combo"] == 1.0 and e["claude"] == e["claude2"] == pytest.approx(0.7)
    assert "跌破季線" not in notes["combo"] and "跌破季線" in notes["claude"]
    assert all(v == 1.0 for mid, v in e.items() if mid not in ("combo", "claude", "claude2"))
    e, notes = decide({"light": "紅燈", "above_ma60": True, "above_ma200_month_end": False, "vix": 18.0}, FLAGS)
    assert e["combo"] == pytest.approx(0.7) and e["claude"] == e["claude2"] == 1.0 and "上月底大盤低於年線" in notes["combo"]


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
    return runner.run_variant("baseline", ins, man, uni=UNI), runner.run_variant("E2", ins, man, uni=UNI)


def test_variant_registered_and_request_file_valid():
    assert runner.VARIANTS["E2"] == FLAGS
    assert request.load_request("research/requests/102-e2.json") == [
        ["run", "--variant", "baseline", "--variant", "E2"], ["compare", "--base", "baseline", "--variant", "E2"]]


def test_research_run_changes_only_combo(runs):
    base, e2 = runs
    for mid in runner.METHOD_IDS:
        same = e2["methods"][mid]["equity"] == base["methods"][mid]["equity"] and e2["methods"][mid]["trades"] == base["methods"][mid]["trades"]
        assert same == (mid != "combo"), mid


def test_flip_diagnostic_is_emitted_for_every_run_and_matches_index_data(runs, data):
    base, e2 = runs
    b, ins = data
    assert base["regime"] == e2["regime"]   # 診斷只看大盤，和旗標無關
    tw = ins["px"]["^TWII"]
    old, new = [], []
    for day in base["dates"]:   # 每個評估日都只用到當天為止的大盤資料重算一次
        n = tw["dates"].index(day) + 1
        c = tw["close"][:n]
        old.append(c[-1] < sum(c[-60:]) / 60)
        new.append(_brute({"dates": tw["dates"][:n], "close": c}, day) is False)
    g = base["regime"]
    assert g["all"]["below_ma60"] == sum(old) > 0 and g["all"]["below_ma200_month"] == sum(new) > 0
    count = lambda xs: sum(x != y for x, y in zip(xs, xs[1:]))  # noqa: E731
    assert g["flips"]["all"] == {"below_ma60": count(old), "below_ma200_month": count(new)}
    assert count(old) > count(new) >= 1   # 合成資料：月底年線訊號翻得比每日季線少
    for key in ("below_ma60", "below_ma200_month"):
        assert sum(f[key] for f in g["flips"]["folds"]) == g["flips"]["all"][key]
        assert sum(f[key] for f in g["folds"]) == g["all"][key]
    assert len(g["flips"]["folds"]) == len(base["folds"])
    md = report.result_markdown(base)
    assert "## 趨勢訊號（假設 E2 的診斷）" in md
    assert f"| 全期 | {sum(old)} | {count(old)} | {sum(new)} | {count(new)} |" in md
    cmp = report.compare(base, e2, [], n_boot=50)
    assert cmp["regime"]["flips"] == g["flips"] and cmp["methods"]["combo"]["affected"]
    report.compare_markdown(cmp)


def test_combo_exposure_follows_month_end_signal(data, monkeypatch):
    """整段跑的時候，combo 每天拿到的持股比例＝只用當天以前的大盤資料算出來的月底年線訊號。"""
    b, ins = data
    seen = []
    real = engine.plan_orders

    def plan(state, mid, acc, ranking, day, px, sym, expo=1.0):
        if mid == "combo":
            seen.append((day, expo))
        return real(state, mid, acc, ranking, day, px, sym, expo)
    monkeypatch.setattr(engine, "plan_orders", plan)
    runner.simulate(ins, FLAGS, b["warmup_end"], uni=UNI)
    tw, vix = ins["px"]["^TWII"], ins["px"]["^VIX"]
    assert len(seen) > 100 and len({e for _, e in seen}) > 1
    for day, expo in seen:
        n = tw["dates"].index(day) + 1
        below = _brute({"dates": tw["dates"][:n], "close": tw["close"][:n]}, day) is False
        v = bt.vix_before(vix, day)
        assert expo == pytest.approx(max(0.3, 1.0 - 0.3 * below - 0.2 * (v is not None and v >= 25)))


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
            ctx["regime"]["above_ma200_month_end"] = methods.month_end_trend(px.get("^TWII"), day)
            if flags is not None:
                ctx["variant"], ctx["memo"] = flags, memo
            state = engine.run_day(state, ctx, dates, px, sym, names)
            state["checkpoint"] = None
    finally:
        C.METHODS, C.TRADING_DAYS = keep_methods, keep_days
    return state


def test_claude_accounts_unaffected(data):
    b, ins = data
    off, on = _run_all(ins, None, b["warmup_end"], UNI), _run_all(ins, FLAGS, b["warmup_end"], UNI)
    assert {"claude", "claude2", "combo"} <= set(on["accounts"])
    for mid, acc in on["accounts"].items():
        assert (acc == off["accounts"][mid]) == (mid != "combo"), mid
    assert any("降低持股比例" in t["reason"] for t in off["accounts"]["claude"]["trades"])   # Claude 判斷的持股比例真的有在動
