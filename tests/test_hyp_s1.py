"""假設 S1：oneil、tech4 的停損漲跌幅改用含息價格（收盤＋進場後累計每股現金股利）。全部用合成資料。"""
import copy

import pytest

from papertrade import backtest as bt
from papertrade import config as C
from papertrade import engine
from papertrade.research import dataset, report, request, runner
from tests.test_research import UNI, make

FLAGS = {"dividend_aware_stop": True}
DAYS = ["2026-03-02", "2026-03-03", "2026-03-04", "2026-03-05"]
SYM = {"A": "A.TW"}


def _px(close, div=None):
    s = {"dates": DAYS[:len(close)], "open": list(close), "close": list(close), "volume": [1e6] * len(close)}
    if div is not None:
        s["div"] = div
    return {"A.TW": s}


def _plan(mid, flags, close, div_cash=None, shares=1000, entry=100.0):
    """進場價 entry 的持股，今天收盤 close、進場以來領到 div_cash 元。回傳 (委託, state)。"""
    state = engine.new_state()
    state["days"] = DAYS[:2]
    if flags is not None:
        state["variant"] = flags
    acc = state["accounts"].setdefault(mid, engine.new_account())
    acc["positions"]["A"] = {"shares": shares, "price": entry, "cost": shares * entry * 1.001425, "date": DAYS[0], "reason": "測試"}
    if div_cash is not None:
        acc["positions"]["A"]["div"] = div_cash
    ranking = [{"code": "A", "score": 1.0, "reason": "測試", "votes": 3}]
    return engine.plan_orders(state, mid, acc, ranking, DAYS[1], _px([entry, close]), SYM), state


# ---------- 規則 ----------

@pytest.mark.parametrize("mid", ["oneil", "tech4"])
def test_dividend_is_added_back_for_target_methods(mid):
    # 進場 100、除息 5 元後收 91：不含息 -9%（原規則停損），含息 -4%（不停損）
    plan, state = _plan(mid, FLAGS, 91.0, div_cash=5000.0)
    assert plan["sells"] == []
    assert state["stop_diag"] == [{"method": mid, "date": DAYS[1], "code": "A", "entry": DAYS[0],
                                   "raw_chg": pytest.approx(-9.0), "adj_chg": pytest.approx(-4.0)}]
    # 每股股利＝累計金額 ÷ 股數：同樣 5000 元、股數 2500 股時每股只有 2 元，含息 -7% 仍不停損；每股 0.5 元就停損
    assert _plan(mid, FLAGS, 91.0, div_cash=5000.0, shares=2500)[0]["sells"] == []
    plan, state = _plan(mid, FLAGS, 91.0, div_cash=5000.0, shares=10000)
    assert len(plan["sells"]) == 1 and "含息 -8.5%" in plan["sells"][0]["reason"] and "停損" in plan["sells"][0]["reason"]
    assert "stop_diag" not in state   # 兩種算法都停損，不是「改判」事件
    # 含息後仍然跌破 -8%：照樣停損，門檻沒變
    plan, _ = _plan(mid, FLAGS, 86.0, div_cash=5000.0)
    assert len(plan["sells"]) == 1 and "觸發 -8% 停損" in plan["sells"][0]["reason"]
    assert _plan(mid, FLAGS, 87.5, div_cash=5000.0)[0]["sells"] == []   # 含息 -7.5%
    # 沒領過股利：和原規則一模一樣（連理由文字都相同）
    assert _plan(mid, FLAGS, 91.0)[0] == _plan(mid, None, 91.0)[0] == _plan(mid, FLAGS, 91.0, div_cash=0.0)[0]
    assert _plan(mid, FLAGS, 91.0)[0]["sells"] == [{"code": "A", "reason": "跌 -9.0%，觸發 -8% 停損"}]


def test_take_profit_and_max_hold_still_use_raw_price():
    # tech4 停利 +10%：收 108、領過 5 元，含息 +13% 但不含息只有 +8% → 不停利（S1 只改停損）
    assert _plan("tech4", FLAGS, 108.0, div_cash=5000.0)[0]["sells"] == []
    plan, _ = _plan("tech4", FLAGS, 110.0, div_cash=5000.0)
    assert plan == _plan("tech4", None, 110.0, div_cash=5000.0)[0] and "停利" in plan["sells"][0]["reason"]


@pytest.mark.parametrize("flags", [None, {}, {"dividend_aware_stop": False}, {"other": True}])
@pytest.mark.parametrize("mid", ["oneil", "tech4", "claude", "claude2"])
def test_flag_off_is_the_original_rule(mid, flags):
    plan, state = _plan(mid, flags, 89.0, div_cash=5000.0)   # claude2 的門檻是 -10%，用 -11%
    limit = next(m for m in C.METHODS if m["id"] == mid)["stop_loss"]
    assert plan["sells"] == [{"code": "A", "reason": f"跌 -11.0%，觸發 {limit}% 停損"}] and "stop_diag" not in state


@pytest.mark.parametrize("mid", ["claude", "claude2"])
def test_claude_accounts_ignore_the_flag(mid):
    """旗標開著，Claude 判斷（共用同一段停損程式）仍然用不含息的漲跌幅。"""
    for close in (91.5, 89.0, 80.0):
        on, state = _plan(mid, FLAGS, close, div_cash=5000.0)
        assert on == _plan(mid, None, close, div_cash=5000.0)[0] and "stop_diag" not in state
    assert len(_plan("claude", FLAGS, 91.5, div_cash=5000.0)[0]["sells"]) == 1


def test_injected_method_with_stop_loss_is_unaffected(monkeypatch):
    """任何不在目標清單裡、但也有 stop_loss 的方法（這裡臨時塞一個）都不受旗標影響。"""
    monkeypatch.setattr(C, "METHODS", [*C.METHODS, {"id": "probe", "name": "測試", "stop_loss": -8, "max_hold": 20}])
    on, state = _plan("probe", FLAGS, 91.0, div_cash=5000.0)
    assert on["sells"] == [{"code": "A", "reason": "跌 -9.0%，觸發 -8% 停損"}] and "stop_diag" not in state
    assert engine.STOP_VARIANT_METHODS == ("oneil", "tech4")


def test_engine_days_ex_dividend_drop(monkeypatch):
    """用引擎實際走一遍：3/3 開盤買進，3/4 除息 6 元、收盤跌到 91。原規則 3/5 開盤停損；S1 續抱。"""
    px = _px([100.0, 100.0, 91.0, 92.0], div=[0.0, 0.0, 6.0, 0.0])
    monkeypatch.setitem(engine.METHOD_FNS, "oneil", lambda ctx: [])

    def run(flags):
        with runner.patched_config({}):
            state = engine.new_state()
            state["variant"] = flags
            state["accounts"]["oneil"]["pending"] = {"decided": DAYS[0], "sells": [], "buys": [{"code": "A", "amount": 200_000, "reason": "測試"}]}
            state["last_decision"] = DAYS[0]
            for i in range(1, 4):
                cut = {k: {f: v[:i + 1] for f, v in s.items()} for k, s in px.items()}
                for mid in C.METHODS:
                    monkeypatch.setitem(engine.METHOD_FNS, mid["id"], lambda ctx: [])
                state = engine.run_day(state, {"regime": {}, "variant": flags}, DAYS[:i + 1], cut, SYM, {})
            return state
    base, s1 = run({}), run(FLAGS)
    a, b = base["accounts"]["oneil"], s1["accounts"]["oneil"]
    assert [t["side"] for t in a["trades"]] == ["買", "賣"] and a["trades"][1]["date"] == DAYS[3] and "停損" in a["trades"][1]["reason"]
    assert [t["side"] for t in b["trades"]] == ["買"] and "A" in b["positions"]
    shares = b["positions"]["A"]["shares"]
    assert b["positions"]["A"]["div"] == pytest.approx(shares * 6.0)
    assert s1["stop_diag"][0]["raw_chg"] == pytest.approx(-9.0) and s1["stop_diag"][0]["adj_chg"] == pytest.approx(-3.0)
    assert "stop_diag" not in base


# ---------- 診斷的「之後報酬」 ----------

def test_spared_stops_after_return():
    px = {"A.TW": {"dates": ["d1", "d2", "d3", "d4", "d5"], "open": [100.0, 90.0, 92.0, 95.0, 99.0], "close": [91.0, 91.0, 93.0, 96.0, 98.0],
                   "div": [0.0, 1.0, 0.0, 2.0, 0.0]}}
    ev = {"method": "oneil", "date": "d1", "code": "A", "entry": "d0", "raw_chg": -9.0, "adj_chg": -4.0, "symbol": "A.TW"}
    dup = {**ev, "date": "d2", "raw_chg": -9.5}   # 同一筆持股第二天又符合：只算一次
    sell = {"date": "d4", "side": "賣", "code": "A", "price": 95.0, "held_from": "d0", "reason": "已持有 20 個交易日，依方法出場"}
    other = {"date": "d3", "side": "賣", "code": "A", "price": 1.0, "held_from": "dX", "reason": "別筆持股"}
    got = runner.spared_stops([ev, dup], [other, sell], px, "d1", "d5")
    # 原規則 d2 開盤 90 出場；實際 d4 開盤 95 出場，中間 d4 除息 2 元（d2 當天除息的兩邊都領得到，不算）
    assert got["count"] == 1 and got["events"][0]["after_return"] == pytest.approx((95.0 + 2.0) / 90.0 - 1) == got["mean_after_return"]
    assert got["events"][0]["exit_date"] == "d4" and got["events"][0]["raw_chg"] == -9.0 and "symbol" not in got["events"][0]
    # 到期末還沒出場：用期末收盤價；期間以外的事件不算；只用到 end 為止的資料
    still = runner.spared_stops([ev], [], px, "d1", "d5")["events"][0]
    assert still["after_return"] == pytest.approx((98.0 + 2.0) / 90.0 - 1) and still["exit_reason"] == "期末仍持有"
    cut = runner.spared_stops([ev], [sell], px, "d1", "d3")["events"][0]
    assert cut["after_return"] == pytest.approx(93.0 / 90.0 - 1) and cut["exit_date"] is None
    assert runner.spared_stops([ev], [sell], px, "d2", "d5") == {"count": 0, "mean_after_return": None, "events": []}
    # 隔天就因為別的規則出場：和原規則同一個價格，之後報酬 0；事件在最後一天：算不出來
    assert runner.spared_stops([ev], [{**sell, "date": "d2", "price": 90.0}], px, "d1", "d5")["events"][0]["after_return"] == 0
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
def crafted(data):
    """找出 baseline 裡一筆停損（決策日之前就已進場），在它的決策日塞一筆大額現金股利：
    股價不變，所以不含息的漲跌幅照樣跌破 -8%，含息之後就不會。"""
    b, ins = data
    man = {**b, "insample_sha256": "x" * 64}
    base0 = runner.run_variant("baseline", ins, man, uni=UNI)
    cal = bt.calendar(ins["px"])
    mid, t = next((mid, t) for mid in ("tech4", "oneil") for t in base0["methods"][mid]["trades"]
                  if t["side"] == "賣" and "停損" in t["reason"] and t["held_from"] < cal[cal.index(t["date"]) - 1])
    decided = cal[cal.index(t["date"]) - 1]
    ds = copy.deepcopy(ins)
    s = ds["px"][UNI[0][t["code"]]]
    i = s["dates"].index(decided)
    s["div"][i] = round(s["close"][i] * 0.3, 2)
    return ds, man, mid, t, decided, runner.run_variant("baseline", ds, man, uni=UNI), runner.run_variant("S1", ds, man, uni=UNI)


def test_variant_registered_and_request_file_valid():
    assert runner.VARIANTS["S1"] == FLAGS
    assert request.load_request("research/requests/104-s1.json") == [
        ["run", "--variant", "baseline", "--variant", "S1"], ["compare", "--base", "baseline", "--variant", "S1"]]


def test_research_run_spares_the_ex_dividend_stop(crafted):
    ds, man, mid, t, decided, base, s1 = crafted
    key = lambda x: (x["date"], x["code"], x["side"])  # noqa: E731
    assert key(t) in {key(x) for x in base["methods"][mid]["trades"]}          # baseline 仍然在那天停損
    assert not any(key(x) == key(t) and "停損" in x["reason"] for x in s1["methods"][mid]["trades"])
    for m in runner.METHOD_IDS:   # 只有 oneil、tech4 可能改變
        same = s1["methods"][m]["equity"] == base["methods"][m]["equity"] and s1["methods"][m]["trades"] == base["methods"][m]["trades"]
        assert same or m in ("oneil", "tech4"), m
    assert s1["methods"][mid]["trades"] != base["methods"][mid]["trades"]
    assert all("spared_stops" not in m for m in base["methods"].values())
    assert {m for m, v in s1["methods"].items() if "spared_stops" in v} == {"oneil", "tech4"}
    d = s1["methods"][mid]["spared_stops"]
    ev = next(e for e in d["events"] if e["code"] == t["code"] and e["date"] == decided)
    assert ev["entry"] == t["held_from"] and ev["raw_chg"] <= -8 < ev["adj_chg"] and d["count"] == len(d["events"]) >= 1
    # 之後報酬：照定義用資料重算
    s = ds["px"][UNI[0][t["code"]]]
    i = s["dates"].index(decided) + 1
    sell = next((x for x in s1["methods"][mid]["trades"] if x["side"] == "賣" and x["code"] == t["code"] and x["held_from"] == t["held_from"]), None)
    j = s["dates"].index(sell["date"]) if sell else len(s["dates"]) - 1
    want = ((sell["price"] if sell else s["close"][j]) + sum(s["div"][i + 1:j + 1])) / s["open"][i] - 1
    assert ev["after_return"] == pytest.approx(want) and ev["exit_date"] == (sell["date"] if sell else None)
    md = report.result_markdown(s1)
    assert f"含息後不停損的事件 {d['count']} 筆" in md and "含息停損（假設 S1）" not in report.result_markdown(base)
    import json
    assert json.loads(json.dumps(report.copy_slim(s1)))["methods"][mid]["spared_stops"]["count"] == d["count"]
    cmp = report.compare(base, s1, [], n_boot=50)
    assert cmp["methods"][mid]["affected"] and not cmp["methods"]["combo"]["affected"]


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


def test_claude_accounts_unaffected_in_full_run(crafted):
    ds, man, mid, *_ = crafted
    off, on = _run_all(ds, None, man["warmup_end"], UNI), _run_all(ds, FLAGS, man["warmup_end"], UNI)
    on.pop("variant"), on.pop("stop_diag", None)
    assert {"claude", "claude2"} <= set(on["accounts"])
    for m, acc in on["accounts"].items():
        assert acc == off["accounts"][m] or m in ("oneil", "tech4"), m
    assert on["accounts"][mid] != off["accounts"][mid]
    stops = [t for m in ("claude", "claude2") for t in off["accounts"][m]["trades"] if "停損" in t.get("reason", "")]
    assert stops and any(a.get("dividends") for m, a in off["accounts"].items() if m in ("claude", "claude2"))   # 它們真的有停損、也有領股利
