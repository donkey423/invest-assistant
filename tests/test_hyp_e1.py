"""假設 E1：combo 降低持股比例時每檔等比例部分減碼、回升時等比例補回。全部用合成資料。"""
import copy

import pytest

from papertrade import backtest as bt
from papertrade import config as C
from papertrade import engine, metrics
from papertrade.research import dataset, report, request, runner
from tests.test_research import UNI, make

FLAGS = {"proportional_trim": True}
DAY, NEXT = "2026-03-02", "2026-03-03"
CODES5 = ["A", "B", "C", "D", "E"]
SYM = {c: c + ".TW" for c in [*CODES5, "F"]}
PRICES = {"A": 100.0, "B": 50.0, "C": 200.0, "D": 80.0, "E": 125.0, "F": 40.0}
PX = {SYM[c]: {"dates": [DAY, NEXT], "open": [p, p], "close": [p, p], "volume": [1e6, 1e6]} for c, p in PRICES.items()}


def _account(weights: dict, equity: float = 1_000_000.0) -> dict:
    """weights＝各檔市值占淨值的比例，其餘是現金。"""
    acc = engine.new_account()
    for code, w in weights.items():
        shares = round(equity * w / PRICES[code])
        acc["positions"][code] = {"shares": shares, "price": PRICES[code], "cost": round(shares * PRICES[code] * 1.001425, 2),
                                  "date": "2026-02-02", "reason": "測試"}
    acc["cash"] = equity - engine.market_value(acc, DAY, PX, SYM)
    return acc


def _state(flags=None, mid="combo", acc=None) -> dict:
    state = engine.new_state()
    state["days"] = ["2026-02-02", DAY]
    if flags is not None:
        state["variant"] = flags
    if acc is not None:
        state["accounts"][mid] = acc
    return state


def _plan(acc, flags, expo, mid="combo", ranked=CODES5):
    ranking = [{"code": c, "score": 1.0, "reason": "測試", "votes": 3} for c in ranked]
    return engine.plan_orders(_state(flags, mid, acc), mid, acc, ranking, DAY, PX, SYM, expo)


def _fill(acc, plan):
    acc["pending"] = plan
    engine._fill(acc, NEXT, PX, SYM, {})
    return acc


# ---------- 旗標關閉：和原本完全相同 ----------

def test_flag_off_keeps_whole_position_sells():
    acc = _account({c: 0.2 for c in CODES5})
    want = {"decided": DAY, "sells": [{"code": "E", "reason": "降低持股比例"}, {"code": "D", "reason": "降低持股比例"}], "buys": []}
    assert _plan(copy.deepcopy(acc), None, 0.7) == want == _plan(copy.deepcopy(acc), {}, 0.7)
    assert _plan(copy.deepcopy(acc), {"proportional_trim": False}, 0.7) == want
    low = _account({c: 0.14 for c in CODES5})   # 比例回升：原本不會補回既有持股
    assert _plan(low, None, 1.0)["buys"] == []


def test_flag_only_touches_combo():
    """旗標開著，Claude 判斷（同樣吃持股比例）與其他方法的委託還是原本的整檔賣出、不補回。"""
    for mid in ("claude", "claude2", "momentum", "oneil"):
        acc = _account({c: 0.2 for c in CODES5})
        assert _plan(copy.deepcopy(acc), FLAGS, 0.7, mid) == _plan(copy.deepcopy(acc), None, 0.7, mid)
        assert all("shares" not in s for s in _plan(copy.deepcopy(acc), FLAGS, 0.7, mid)["sells"])
        low = _account({c: 0.14 for c in CODES5})
        assert _plan(low, FLAGS, 1.0, mid)["buys"] == []


# ---------- 等比例減碼 ----------

def test_trim_sells_same_fraction_of_every_position():
    acc = _account({"A": 0.3, "B": 0.25, "C": 0.2, "D": 0.15, "E": 0.1})
    before = {c: p["shares"] for c, p in acc["positions"].items()}
    plan = _plan(acc, FLAGS, 0.7)
    assert [s["code"] for s in plan["sells"]] == CODES5 and plan["buys"] == []
    for s in plan["sells"]:
        assert s["shares"] == int(before[s["code"]] * 0.3) and s["reason"].startswith("降低持股比例：每檔等比例減碼 30.0%")
    _fill(acc, plan)
    assert set(acc["positions"]) == set(CODES5)   # 一檔都沒有被整檔賣掉
    mv = engine.market_value(acc, NEXT, PX, SYM)
    assert mv == pytest.approx(700_000, rel=2e-3) and mv >= 700_000   # 無條件捨去股數，所以略高於目標
    for c in CODES5:   # 各檔之間的比重不變
        assert acc["positions"][c]["shares"] / before[c] == pytest.approx(0.7, abs=2e-3)
    assert all(t["partial"] and t["side"] == "賣" for t in acc["trades"]) and len(acc["trades"]) == 5
    # 減到目標後不會再觸發，也沒有空間買新股
    again = _plan(acc, FLAGS, 0.7, ranked=["F", *CODES5])
    assert again["sells"] == [] and again["buys"] == []


def test_trim_uses_existing_band():
    acc = _account({c: 0.2 for c in CODES5})
    assert _plan(acc, FLAGS, 0.92)["sells"] == []        # 1.0 ≤ 0.92 × 1.1：不動
    assert len(_plan(acc, FLAGS, 0.90)["sells"]) == 5    # 1.0 > 0.90 × 1.1


def test_rank_exit_still_sells_whole_position_before_trim():
    acc = _account({c: 0.2 for c in CODES5})
    ranked = ["A", "B", "C", "D", *[f"X{i}" for i in range(10)]]   # E 掉出前 10 名
    plan = _plan(acc, FLAGS, 0.6, ranked=ranked)
    assert plan["sells"][0] == {"code": "E", "reason": "已不在前 10 名"}
    assert [s["code"] for s in plan["sells"][1:]] == ["A", "B", "C", "D"] and all(s["shares"] for s in plan["sells"][1:])
    _fill(acc, plan)
    assert set(acc["positions"]) == {"A", "B", "C", "D"}
    assert engine.market_value(acc, NEXT, PX, SYM) == pytest.approx(600_000, rel=2e-3)


def test_partial_sell_accounting():
    acc = engine.new_account()
    acc["positions"]["A"] = {"shares": 1000, "price": 90.0, "cost": 90_128.25, "date": "2026-02-02", "reason": "測試", "div": 2000.0}
    whole = copy.deepcopy(acc)
    _fill(acc, {"decided": DAY, "sells": [{"code": "A", "shares": 300, "reason": "降低持股比例：測試"}], "buys": []})
    gross = 300 * 100.0
    cost_out = gross * (C.FEE_RATE + C.TAX_RATE)
    pos, t = acc["positions"]["A"], acc["trades"][0]
    assert acc["cash"] == pytest.approx(1_000_000 + gross - cost_out) and acc["fees"] == pytest.approx(cost_out)
    assert (pos["shares"], pos["price"], pos["date"]) == (700, 90.0, "2026-02-02")
    assert pos["cost"] == pytest.approx(90_128.25 * 0.7, abs=0.01) and pos["div"] == pytest.approx(1400.0)   # 每股成本、每股已領股利不變
    pnl = gross - cost_out - 90_128.25 * 0.3
    assert t["shares"] == 300 and t["partial"] is True and t["pnl"] == round(pnl) and t["fee"] == round(cost_out)
    assert t["pnl_pct"] == pytest.approx(pnl / (90_128.25 * 0.3) * 100, abs=0.01) and t["held_from"] == "2026-02-02"
    # 之後把剩下的全部賣掉：兩筆損益相加＝一次整檔賣出的損益（手續費沒碰到最低 20 元時）
    acc["trades"] = []
    _fill(acc, {"decided": DAY, "sells": [{"code": "A", "reason": "測試"}], "buys": []})
    _fill(whole, {"decided": DAY, "sells": [{"code": "A", "reason": "測試"}], "buys": []})
    assert "A" not in acc["positions"] and "partial" not in acc["trades"][0] and "partial" not in whole["trades"][0]
    assert acc["cash"] == pytest.approx(whole["cash"]) and acc["fees"] == pytest.approx(whole["fees"])
    assert t["pnl"] + acc["trades"][0]["pnl"] == pytest.approx(whole["trades"][0]["pnl"], abs=1)
    # 委託股數超過持有股數：當成整檔賣出
    acc2 = copy.deepcopy(whole)
    acc2["positions"]["A"] = {"shares": 10, "price": 90.0, "cost": 920.0, "date": "2026-02-02", "reason": "測試"}
    _fill(acc2, {"decided": DAY, "sells": [{"code": "A", "shares": 99, "reason": "測試"}], "buys": []})
    assert "A" not in acc2["positions"] and acc2["trades"][-1]["shares"] == 10


# ---------- 等比例補回 ----------

def test_topup_restores_existing_positions_proportionally():
    acc = _account({"A": 0.3, "B": 0.25, "C": 0.2, "D": 0.15, "E": 0.1}, equity=700_000)
    acc["cash"] += 300_000   # 持股 70%、現金 30%
    before = copy.deepcopy(acc["positions"])
    plan = _plan(acc, FLAGS, 1.0, ranked=["F", *CODES5])
    assert plan["sells"] == [] and [b["code"] for b in plan["buys"]] == CODES5 and all(b["add"] for b in plan["buys"])
    assert sum(b["amount"] for b in plan["buys"]) == pytest.approx(300_000, abs=100)
    assert plan["buys"][0]["reason"].startswith("持股比例回升：每檔等比例補回")
    _fill(acc, plan)
    assert set(acc["positions"]) == set(CODES5)   # 持有的股票不變，沒有買進 F
    for c in CODES5:
        pos = acc["positions"][c]
        assert pos["shares"] / before[c]["shares"] == pytest.approx(1 / 0.7, rel=5e-3)   # 每檔加同樣的比例
        assert pos["date"] == before[c]["date"] and pos["price"] == PRICES[c]            # 進場日不動；同價加碼，均價不變
        assert pos["cost"] > before[c]["cost"]
    assert 0 <= acc["cash"] < 5_000 and all(t["partial"] and t["side"] == "買" for t in acc["trades"])
    assert _plan(acc, FLAGS, 1.0)["buys"] == []   # 補到目標後不再觸發


def test_topup_band_cash_limit_and_reserved_slots():
    near = _account({c: 0.185 for c in CODES5})   # 92.5% ≥ 目標的 0.9 倍：不動
    assert _plan(near, FLAGS, 1.0)["buys"] == []
    # 現金不夠補到目標：有多少補多少。E 掉出前 10 名整檔賣出（估 99.5% 入帳）、買進新股 F 之後，剩下的現金比缺口少
    poor = _account({c: 0.16 for c in CODES5})
    plan = _plan(poor, FLAGS, 1.0, ranked=["F", "A", "B", "C", "D", *[f"X{i}" for i in range(9)]])
    assert plan["sells"] == [{"code": "E", "reason": "已不在前 10 名"}] and plan["buys"][0] == {"code": "F", "amount": 200_000, "reason": "測試"}
    add = plan["buys"][1:]
    assert [b["code"] for b in add] == ["A", "B", "C", "D"] and sum(b["amount"] for b in add) == pytest.approx(159_200, abs=5)
    _fill(poor, plan)
    assert poor["cash"] >= 0 and len(poor["trades"]) == 6 and set(poor["positions"]) == {"A", "B", "C", "D", "F"}
    # 只抱 3 檔、另外 2 個檔位照舊留給新股（每檔 20%），既有持股只補到 60%
    three = _account({"A": 0.15, "B": 0.15, "C": 0.15})
    plan = _plan(three, FLAGS, 1.0, ranked=["A", "B", "C", "D", "E"])
    new, add = [b for b in plan["buys"] if not b.get("add")], [b for b in plan["buys"] if b.get("add")]
    assert [(b["code"], b["amount"]) for b in new] == [("D", 200_000), ("E", 200_000)]
    assert [b["code"] for b in add] == ["A", "B", "C"] and sum(b["amount"] for b in add) == pytest.approx(150_000, abs=5)
    # 沒有新股可買時，空檔位的額度也不會灌進既有持股
    plan = _plan(three, FLAGS, 1.0, ranked=["A", "B", "C"])
    assert sum(b["amount"] for b in plan["buys"]) == pytest.approx(150_000, abs=5) and all(b["add"] for b in plan["buys"])
    empty = engine.new_account()   # 空手：只有一般買進
    assert all(not b.get("add") for b in _plan(empty, FLAGS, 1.0)["buys"])


def test_add_order_never_opens_a_position_and_plain_buy_never_adds():
    acc = _account({"A": 0.2})
    shares = acc["positions"]["A"]["shares"]
    _fill(acc, {"decided": DAY, "sells": [], "buys": [{"code": "B", "add": True, "amount": 50_000, "reason": "x"},
                                                       {"code": "A", "amount": 50_000, "reason": "x"}]})
    assert set(acc["positions"]) == {"A"} and acc["positions"]["A"]["shares"] == shares and not acc["trades"]


# ---------- 整段跑：只有 combo 受影響、帳對得起來 ----------

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
    return runner.run_variant("baseline", ins, man, uni=UNI), runner.run_variant("E1", ins, man, uni=UNI)


def test_variant_registered_and_request_file_valid():
    assert runner.VARIANTS["E1"] == FLAGS
    assert request.load_request("research/requests/101-e1.json") == [
        ["run", "--variant", "baseline", "--variant", "E1"], ["compare", "--base", "baseline", "--variant", "E1"]]


def test_research_run_changes_only_combo(runs):
    base, e1 = runs
    assert base["regime"]["all"]["below_ma60"] > 0   # 合成資料裡大盤有跌破季線，持股比例真的有變
    for mid in runner.METHOD_IDS:
        same = e1["methods"][mid]["equity"] == base["methods"][mid]["equity"] and e1["methods"][mid]["trades"] == base["methods"][mid]["trades"]
        assert same == (mid != "combo")
    assert not any(t.get("partial") for m in base["methods"].values() for t in m["trades"])
    parts = [t for t in e1["methods"]["combo"]["trades"] if t.get("partial")]
    assert any(t["side"] == "賣" for t in parts) and all(("降低持股比例" if t["side"] == "賣" else "持股比例回升") in t["reason"] for t in parts)
    assert not any(t["reason"] == "降低持股比例" for t in e1["methods"]["combo"]["trades"])   # 不再整檔賣出
    assert any(t["reason"] == "降低持股比例" for t in base["methods"]["combo"]["trades"])


def test_metrics_with_partial_trades(runs, data):
    base, e1 = runs
    m = e1["methods"]["combo"]
    a, trades = m["all"], m["trades"]
    assert a["n_trades"] == len(trades) == sum(f["n_trades"] for f in m["folds"])
    assert a["fees"] == pytest.approx(sum(t["fee"] for t in trades))
    eq = [C.START_CASH, *m["equity"]]
    eq[-1] -= a["exit_cost"]
    assert a["turnover"] == pytest.approx(metrics.turnover(trades, eq))   # 成交金額只算實際賣掉／買進的股數
    sells = [t for t in trades if t["side"] == "賣"]
    assert a["win_rate"] == pytest.approx(sum(t["pnl"] > 0 for t in sells) / len(sells))
    # 持股重疊率：部分減碼不算「賣掉」。由交易紀錄還原的每日持股檔數要和引擎當天實際的檔數一樣
    sim = runner.simulate(data[1], FLAGS, data[0]["warmup_end"], uni=UNI)
    assert sim["methods"]["combo"]["trades"] == trades
    assert [len(h) for h in report._held(m, e1["dates"])] == sim["methods"]["combo"]["positions"]
    assert 0 < report.overlap(m, base["methods"]["combo"], e1["dates"]) <= 1
    cmp = report.compare(base, e1, [], n_boot=50)
    assert cmp["methods"]["combo"]["affected"] and not cmp["methods"]["momentum"]["affected"]
    slim = report.copy_slim(e1)["methods"]["combo"]["trades"]
    assert any(t.get("partial") for t in slim) and "partial" not in report.copy_slim(base)["methods"]["combo"]["trades"][0]


def _run_all(ds, flags, start, uni, n_days=110):
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


def test_claude_accounts_unaffected_and_cash_reconciles(data):
    b, ins = data
    off, on = _run_all(ins, None, b["warmup_end"], UNI), _run_all(ins, FLAGS, b["warmup_end"], UNI)
    assert {"claude", "claude2", "combo"} <= set(on["accounts"])
    for mid, acc in on["accounts"].items():
        assert (acc == off["accounts"][mid]) == (mid != "combo"), mid
    assert any("降低持股比例" in t["reason"] for t in off["accounts"]["claude"]["trades"] + off["accounts"]["combo"]["trades"])
    assert not any(t.get("partial") for mid, acc in on["accounts"].items() if mid != "combo" for t in acc["trades"])
    # combo 的帳：起始現金 − 買進 + 賣出 + 股利 ＝ 現金；持股成本＝買進成本 − 已賣出部分的成本
    acc = on["accounts"]["combo"]
    assert any(t.get("partial") for t in acc["trades"])
    buys = [t for t in acc["trades"] if t["side"] == "買"]
    sells = [t for t in acc["trades"] if t["side"] == "賣"]
    cash = (C.START_CASH - sum(t["shares"] * t["price"] + t["fee"] for t in buys) + sum(t["shares"] * t["price"] - t["fee"] for t in sells)
            + acc.get("dividends", 0.0))
    assert acc["cash"] == pytest.approx(cash, abs=len(acc["trades"]) * 1.0)   # 交易紀錄的價格、費用有四捨五入
    assert acc["cash"] >= 0 and all(p["shares"] > 0 and p["cost"] > 0 for p in acc["positions"].values())
    realized = sum(t["pnl"] for t in sells)
    open_cost = sum(p["cost"] for p in acc["positions"].values())
    assert acc["cash"] + open_cost == pytest.approx(C.START_CASH + realized + acc.get("dividends", 0.0), abs=len(acc["trades"]) * 1.0)
