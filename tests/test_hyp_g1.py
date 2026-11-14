"""假設 G1：葛拉漢門檻加「今年累計營收年增率 ≥ 0」，缺資料視為不通過。合成資料。"""
import copy
from pathlib import Path

import pytest

pytest.importorskip("papertrade.metrics")

from papertrade import backtest as bt  # noqa: E402
from papertrade import methods  # noqa: E402
from papertrade.research import report, request, runner  # noqa: E402
from tests.test_research import UNI, baseline, full, parts  # noqa: E402,F401 共用合成資料的 fixture

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = {"insample_sha256": "x" * 64}
FLAG = {"graham_revenue_filter": True}


@pytest.fixture(scope="module")
def g1(parts):
    b, ins, _ = parts
    return runner.run_variant("G1", ins, {**b, **MANIFEST}, uni=UNI)


def _ctx(variant=None):
    value = {"A": {"pe": 8.0, "pb": 0.8}, "B": {"pe": 10.0, "pb": 1.0}, "C": {"pe": 12.0, "pb": 1.2},
             "D": {"pe": 6.0, "pb": 0.5}, "E": {"pe": 9.0, "pb": 0.9}, "F": {"pe": 7.0, "pb": 0.7},
             "X": {"pe": 20.0, "pb": 1.0}}                       # X 沒過葛拉漢門檻
    revenue = {"A": {"ym": "2024-05", "yoy": 3.0, "ytd_yoy": 5.0}, "B": {"ym": "2024-05", "yoy": 9.0, "ytd_yoy": -0.01},
               "C": {"ym": "2024-05", "yoy": -4.0, "ytd_yoy": 0.0}, "D": {"ym": "2024-05", "yoy": 30.0, "ytd_yoy": None},
               "F": {"ym": "2024-05", "yoy": -20.0, "ytd_yoy": 12.0}, "X": {"ym": "2024-05", "yoy": 50.0, "ytd_yoy": 50.0}}   # E 完全沒有營收資料
    ctx = {"codes": list(value), "value": value, "revenue": revenue}
    if variant is not None:
        ctx["variant"] = variant
    return ctx


def test_flag_off_is_the_original_graham():
    want = None
    for variant in (None, {}, {"graham_revenue_filter": False}, {"other": True}):
        out = methods.graham(_ctx(variant))
        assert [r["code"] for r in out] == ["D", "F", "A", "E", "B", "C"]
        assert out[0] == {"code": "D", "score": -3.0, "reason": "本益比 6.0、股價淨值比 0.50，葛拉漢數 3.0（≤ 22.5）"}
        want = want or out
        assert out == want
    ctx = _ctx()
    del ctx["revenue"]   # 原版完全不讀營收
    assert methods.graham(ctx) == want


def test_flag_on_requires_non_negative_ytd_revenue_growth_and_data():
    out = methods.graham(_ctx(FLAG))
    # B：-0.01% 不通過；C：剛好 0 通過；D：ytd_yoy 缺值不通過；E：沒有營收資料不通過；F：單月衰退但累計成長，通過
    assert [r["code"] for r in out] == ["F", "A", "C"]
    assert [r["score"] for r in out] == pytest.approx([-4.9, -6.4, -14.4])   # 分數（排序依據）不變
    assert out[2]["reason"] == "本益比 12.0、股價淨值比 1.20，葛拉漢數 14.4（≤ 22.5），今年累計營收 +0.0%（沒有衰退）"
    ctx = _ctx(FLAG)
    ctx["revenue"] = {}
    assert methods.graham(ctx) == []


def test_g1_run_is_a_strict_subset_of_baseline_candidates(parts, baseline, g1):
    b, ins, _ = parts
    cal = bt.calendar(ins["px"])
    i0 = cal.index(b["warmup_end"])
    gra, base = g1["methods"]["graham"], baseline["methods"]["graham"]
    assert gra["all"]["avg_candidates"] < base["all"]["avg_candidates"] and gra["equity"] != base["equity"]
    tables = runner.revenue_tables(ins["rev"])
    for j, picks in enumerate(gra["picks"]):
        day = cal[i0 + j]   # 這次決策只能用到 day 為止已公布的營收
        for code in picks:
            assert runner.revenue_at(tables, code, day)["ytd_yoy"] >= 0
    # 名單＝原版排名剔掉不合格的之後的前 5 名（用原始資料重算）
    for j in (0, 30, len(gra["picks"]) - 1):
        day, ok = cal[i0 + j], []
        for code in UNI[0]:
            v = runner.value_at(ins["val"].get(code), day) or {}
            r = bt.revenue_on(ins["rev"].get(code) or {}, day) or {}
            pe, pb = v.get("pe"), v.get("pb")
            if pe and pb and pe <= 15 and pb <= 1.5 and pe * pb <= 22.5 and r.get("ytd_yoy") is not None and r["ytd_yoy"] >= 0:
                ok.append((pe * pb, code))
        assert sorted(gra["picks"][j]) == sorted(c for _, c in sorted(ok)[:5])
    for mid in runner.METHOD_IDS:
        if mid != "graham":
            assert g1["methods"][mid]["equity"] == baseline["methods"][mid]["equity"]
            assert g1["methods"][mid]["trades"] == baseline["methods"][mid]["trades"]


def test_g1_has_no_lookahead_later_revenue_does_not_change_earlier_days(parts, g1):
    b, ins, _ = parts
    cal = bt.calendar(ins["px"])
    cut_day = cal[cal.index(b["warmup_end"]) + 50]
    short = copy.deepcopy(ins)
    for s in short["px"].values():
        n = sum(1 for d in s["dates"] if d <= cut_day)
        for k in s:
            s[k] = s[k][:n]
    short["rev"] = {c: {ym: x for ym, x in series.items() if bt._avail(ym) <= cut_day} for c, series in short["rev"].items()}
    assert any(len(short["rev"][c]) < len(ins["rev"][c]) for c in short["rev"])
    sim = runner.simulate(short, runner.VARIANTS["G1"], b["warmup_end"], uni=UNI)
    k = len(sim["dates"])
    assert k == 50 and sim["methods"]["graham"]["picks"] == g1["methods"]["graham"]["picks"][:k]
    assert sim["methods"]["graham"]["equity"] == g1["methods"]["graham"]["equity"][:k]


def test_g1_compare_reports_candidates_and_positions(baseline, g1):
    cmp = report.compare(baseline, g1, [], n_boot=20)
    gra = cmp["methods"]["graham"]
    assert gra["affected"] and [m for m, x in cmp["methods"].items() if x["affected"]] == ["graham"]
    assert gra["extra"]["variant"]["avg_candidates"] < gra["extra"]["base"]["avg_candidates"]
    assert gra["extra"]["variant"]["avg_positions"] is not None and gra["picks_overlap"] is not None
    md = report.compare_markdown(cmp)
    assert "平均持股檔數" in md and "排名內的檔數（通過門檻的檔數）平均" in md


def test_g1_variant_and_request_file(monkeypatch):
    assert runner.VARIANTS["G1"] == FLAG
    monkeypatch.chdir(ROOT)
    assert request.load_request("research/requests/104-g1.json") == [
        ["run", "--variant", "baseline", "--variant", "G1"], ["compare", "--base", "baseline", "--variant", "G1"]]
