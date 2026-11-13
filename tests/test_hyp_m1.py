"""假設 M1：動能在大盤低於 200 日均線時不買新股（持股照排名續抱）。合成資料。"""
from pathlib import Path

import pytest

pytest.importorskip("papertrade.metrics")

from papertrade import backtest as bt  # noqa: E402
from papertrade import config as C  # noqa: E402
from papertrade import engine, methods  # noqa: E402
from papertrade.research import report, request, runner  # noqa: E402
from tests.test_research import UNI, baseline, full, parts  # noqa: E402,F401 共用合成資料的 fixture

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def m1(parts):
    b, ins, _ = parts
    return runner.run_variant("M1", ins, {**b, "insample_sha256": "x" * 64}, uni=UNI)


def test_m1_is_config_only_and_live_config_is_untouched():
    assert runner.VARIANTS["M1"] == {"methods": {"momentum": {"market_filter": 200}}}
    live = next(m for m in C.METHODS if m["id"] == "momentum")
    assert "market_filter" not in live
    with runner.patched_config(runner.VARIANTS["M1"]) as ms:
        assert next(m for m in ms if m["id"] == "momentum")["market_filter"] == 200
        assert all("market_filter" not in m for m in ms if m["id"] != "momentum")
    with runner.patched_config(runner.VARIANTS["baseline"]) as ms:
        assert all("market_filter" not in m for m in ms)
    assert next(m for m in C.METHODS if m["id"] == "momentum") is live and "market_filter" not in live


def test_m1_gate_follows_only_data_up_to_the_decision_day(parts, baseline, m1):
    b, ins, _ = parts
    cal = bt.calendar(ins["px"])
    i0 = cal.index(b["warmup_end"])
    tw = ins["px"]["^TWII"]
    closed = []
    for j in range(len(m1["dates"])):   # 第 j 個評估日開盤成交的決策，是在 cal[i0 + j] 收盤做的
        c = [x for d, x in zip(tw["dates"], tw["close"]) if d <= cal[i0 + j]]
        closed.append(c[-1] < sum(c[-200:]) / 200)
    target = m1["methods"]["momentum"]["target_exposure"]
    assert [t == 0.0 for t in target] == closed and set(target) == {0.0, 1.0}
    n_closed = sum(closed)
    assert 0 < n_closed < len(closed)   # 合成資料兩種狀態都有
    assert m1["methods"]["momentum"]["all"]["target"]["days_zero"] == n_closed
    assert baseline["methods"]["momentum"]["all"]["target"]["days_zero"] == 0


def test_m1_never_buys_while_gate_is_closed_and_other_methods_are_identical(baseline, m1):
    mom = m1["methods"]["momentum"]
    closed_days = {d for d, t in zip(m1["dates"], mom["target_exposure"]) if t == 0.0}
    buys = [t for t in mom["trades"] if t["side"] == "買"]
    assert buys and not [t for t in buys if t["date"] in closed_days]
    assert [t for t in baseline["methods"]["momentum"]["trades"] if t["side"] == "買" and t["date"] in closed_days]   # 原版在這些日子有買
    assert mom["picks"] == baseline["methods"]["momentum"]["picks"]   # 排名不變
    # 閘門第一次關閉之前，兩邊完全相同
    first = next(i for i, d in enumerate(m1["dates"]) if d in closed_days)
    assert mom["equity"][:first] == baseline["methods"]["momentum"]["equity"][:first]
    assert mom["equity"] != baseline["methods"]["momentum"]["equity"]
    for mid in runner.METHOD_IDS:
        if mid != "momentum":
            assert m1["methods"][mid]["equity"] == baseline["methods"][mid]["equity"]
            assert m1["methods"][mid]["trades"] == baseline["methods"][mid]["trades"]


def _decide(flags, above_ma200, monkeypatch):
    """持有 A（仍在前 10 名）與 Z（掉出前 10 名），排名前 5 名是 B～F：看閘門開關時的委託。"""
    codes = [chr(ord("A") + i) for i in range(12)] + ["Z"]
    sym = {c: c for c in codes}
    px = {c: {"dates": ["d1"], "open": [100.0], "close": [100.0]} for c in codes}
    ranking = [{"code": c, "score": 100 - i, "reason": "r"} for i, c in enumerate(["B", "C", "D", "E", "F", "A", "G", "H", "I", "J", "K", "L", "Z"])]
    monkeypatch.setitem(methods.METHOD_FNS, "momentum", lambda ctx: ranking)
    ctx = {"codes": codes, "sym": sym, "px": px, "revenue": {}, "value": {}, "chips": {}, "chip_dates": [], "chain_of": {},
           "chains": {}, "ai_watch": [], "regime": {"light": "紅燈", "above_ma60": True, "above_ma200": above_ma200, "vix": 15}}
    with runner.patched_config(flags):
        state = engine.new_state()
        acc = state["accounts"]["momentum"]
        acc["cash"] = 600_000.0
        for c in ("A", "Z"):
            acc["positions"][c] = {"shares": 2000, "price": 100.0, "cost": 200_000.0, "date": "d0", "reason": "r"}
        engine.decide(state, ctx, "d1", px, sym, {})
        return acc["pending"], next(j for j in state["journal"] if j["method"] == "momentum")


def test_m1_closed_gate_blocks_buys_but_keeps_rank_exit(monkeypatch):
    m1_flags = runner.VARIANTS["M1"]
    open_, _ = _decide(m1_flags, True, monkeypatch)
    assert [s["code"] for s in open_["sells"]] == ["Z"] and [x["code"] for x in open_["buys"]] == ["B", "C", "D", "E"]
    shut, journal = _decide(m1_flags, False, monkeypatch)
    assert [s["code"] for s in shut["sells"]] == ["Z"] and shut["sells"][0]["reason"] == "已不在前 10 名"   # 持股照排名規則處理
    assert shut["buys"] == [] and "不買新股" in journal["note"]                                             # A 續抱、不買新股
    unknown, _ = _decide(m1_flags, None, monkeypatch)   # 年線算不出來（歷史不足 200 根）：不擋
    assert unknown == open_
    base, _ = _decide({}, False, monkeypatch)           # 沒有旗標：大盤在年線下照買
    assert base == open_


def test_m1_request_file_is_valid(monkeypatch):
    monkeypatch.chdir(ROOT)
    assert request.load_request("research/requests/101-m1.json") == [
        ["run", "--variant", "baseline", "--variant", "M1"], ["compare", "--base", "baseline", "--variant", "M1"]]


def test_m1_compare_reports_gate_days(baseline, m1):
    cmp = report.compare(baseline, m1, [], n_boot=20)
    mom = cmp["methods"]["momentum"]
    assert mom["affected"] and mom["picks_overlap"] == 1.0
    assert mom["extra"]["variant"]["target"]["days_zero"] > 0 == mom["extra"]["base"]["target"]["days_zero"]
    assert [m for m, x in cmp["methods"].items() if x["affected"]] == ["momentum"]
    assert "為 0（完全不買新股）" in report.compare_markdown(cmp)
