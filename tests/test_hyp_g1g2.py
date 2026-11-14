"""合併試驗 G1G2：先套 G1 的營收濾網，再在通過者之間用 G2 的價值＋動能排序。合成資料。"""
import copy
from pathlib import Path

import pytest

pytest.importorskip("papertrade.metrics")

from papertrade import backtest as bt  # noqa: E402
from papertrade import methods  # noqa: E402
from papertrade.research import request, runner  # noqa: E402
from tests.test_hyp_g2 import _series  # noqa: E402
from tests.test_research import UNI, baseline, full, parts  # noqa: E402,F401 共用合成資料的 fixture

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = {"insample_sha256": "x" * 64}
G1 = {"graham_revenue_filter": True}
G2 = {"graham_value_momentum": True}
BOTH = {**G1, **G2}


@pytest.fixture(scope="module")
def cheap(parts):
    """和 G2 的測試一樣把本益比與淨值比壓低，讓通過葛拉漢門檻的候選夠多，排名才有作用。"""
    b, ins, _ = parts
    ins = copy.deepcopy(ins)
    for col in ins["val"].values():
        col["pe"] = [round(x * 0.6, 2) for x in col["pe"]]
        col["pb"] = [round(x * 0.5, 2) for x in col["pb"]]
    return b, ins


@pytest.fixture(scope="module")
def base(cheap):
    b, ins = cheap
    return runner.run_variant("baseline", ins, {**b, **MANIFEST}, uni=UNI)


@pytest.fixture(scope="module")
def g1g2(cheap):
    b, ins = cheap
    return runner.run_variant("G1G2", ins, {**b, **MANIFEST}, uni=UNI)


def _ctx(variant=None):
    #            葛拉漢數   累計營收    12-1 報酬
    # A  8×0.8  = 6.4      +5%        +30%
    # B 10×1.0  = 10.0     -0.01%     +50%   ← 動能最強，但營收衰退
    # C 12×1.2  = 14.4     0%         -10%
    # D  6×0.5  = 3.0      缺值       -20%   ← 最便宜，但沒有累計營收
    # E  9×0.9  = 8.1      +8%        （歷史不足，算不出動能）
    # F  7×0.7  = 4.9      +12%       +10%
    # X 20×1.0  沒過門檻    +50%       +90%
    value = {"A": {"pe": 8.0, "pb": 0.8}, "B": {"pe": 10.0, "pb": 1.0}, "C": {"pe": 12.0, "pb": 1.2},
             "D": {"pe": 6.0, "pb": 0.5}, "E": {"pe": 9.0, "pb": 0.9}, "F": {"pe": 7.0, "pb": 0.7},
             "X": {"pe": 20.0, "pb": 1.0}}
    revenue = {"A": {"ytd_yoy": 5.0}, "B": {"ytd_yoy": -0.01}, "C": {"ytd_yoy": 0.0}, "D": {"ytd_yoy": None},
               "E": {"ytd_yoy": 8.0}, "F": {"ytd_yoy": 12.0}, "X": {"ytd_yoy": 50.0}}
    px = {c: _series(m) for c, m in {"A": 30, "B": 50, "C": -10, "D": -20, "F": 10, "X": 90}.items()}
    px["E"] = _series(40, n=252)
    ctx = {"codes": list(value), "sym": {c: c for c in value}, "value": value, "px": px, "revenue": revenue}
    if variant is not None:
        ctx["variant"] = variant
    return ctx


def test_variant_is_registered_with_both_flags_and_request_file(monkeypatch):
    assert runner.VARIANTS["G1G2"] == {"graham_revenue_filter": True, "graham_value_momentum": True}
    assert runner.VARIANTS["G1G2"] == {**runner.VARIANTS["G1"], **runner.VARIANTS["G2"]}
    assert runner.VARIANTS["baseline"] == {}
    monkeypatch.chdir(ROOT)
    assert request.load_request("research/requests/106-g1g2.json") == [
        ["run", "--variant", "baseline", "--variant", "G1G2"], ["compare", "--base", "baseline", "--variant", "G1G2"]]


def test_filter_first_then_rank_among_the_survivors():
    out = methods.graham(_ctx(BOTH))
    # 過濾網的＝A、C、E、F；E 算不出動能再排除 → 百分位的母體只有 A、C、F（B、D 不在裡面）
    # 價值百分位：F 1、A 0.5、C 0；動能百分位：A 1、F 0.5、C 0
    score = {r["code"]: r["score"] for r in out}
    assert score == pytest.approx({"F": 0.75, "A": 0.75, "C": 0.0})
    assert [r["code"] for r in out] == ["F", "A", "C"]   # F、A 同分：葛拉漢數低的 F 在前
    assert "今年累計營收 +12.0%（沒有衰退）" in out[0]["reason"] and "價值百分位 100、動能百分位 50，各半" in out[0]["reason"]
    # 順序是「先濾再排」：如果先排再濾，B、D 會留在百分位的母體裡，A 的分數不會是 0.75
    g2_only = {r["code"]: r["score"] for r in methods.graham(_ctx(G2))}
    assert set(g2_only) == {"A", "B", "C", "D", "F"} and g2_only["A"] != pytest.approx(0.75)
    # 選到的一定是兩個單獨變體各自名單的交集
    g1_only = [r["code"] for r in methods.graham(_ctx(G1))]
    assert g1_only == ["F", "A", "E", "C"] and set(score) == set(g1_only) & set(g2_only)


def test_single_flags_and_no_flags_are_unchanged():
    want = methods.graham(_ctx())
    assert [r["code"] for r in want] == ["D", "F", "A", "E", "B", "C"]
    assert want[0] == {"code": "D", "score": -3.0, "reason": "本益比 6.0、股價淨值比 0.50，葛拉漢數 3.0（≤ 22.5）"}
    for variant in ({}, {"graham_revenue_filter": False, "graham_value_momentum": False}, {"other": True}):
        assert methods.graham(_ctx(variant)) == want
    ctx = _ctx()
    del ctx["px"], ctx["sym"], ctx["revenue"]   # 原版不讀股價也不讀營收
    assert methods.graham(ctx) == want
    assert methods.graham(_ctx({**G1, "graham_value_momentum": False})) == methods.graham(_ctx(G1))
    assert methods.graham(_ctx({**G2, "graham_revenue_filter": False})) == methods.graham(_ctx(G2))


def test_g1g2_run_every_pick_passes_the_revenue_filter_and_is_ranked_inside_it(cheap, base, g1g2):
    b, ins = cheap
    sym = UNI[0]
    cal = bt.calendar(ins["px"])
    i0 = cal.index(b["warmup_end"])
    gra, old = g1g2["methods"]["graham"], base["methods"]["graham"]
    assert len(gra["picks"]) == len(old["picks"]) > 0 and any(gra["picks"])
    assert gra["all"]["avg_candidates"] < old["all"]["avg_candidates"] and gra["equity"] != old["equity"]
    tables = runner.revenue_tables(ins["rev"])
    for j, picks in enumerate(gra["picks"]):
        day = cal[i0 + j]   # 這次決策只能用到 day 為止已公布的營收
        for code in picks:
            assert runner.revenue_at(tables, code, day)["ytd_yoy"] >= 0
            v = runner.value_at(ins["val"].get(code), day)
            assert 0 < v["pe"] <= 15 and 0 < v["pb"] <= 1.5 and v["pe"] * v["pb"] <= 22.5
    sizes = []
    for j in (0, 30, len(gra["picks"]) - 1):   # 用到 day 為止的原始資料重算名單：先濾網、再排名
        day, cand = cal[i0 + j], {}
        for code in sym:
            v = runner.value_at(ins["val"].get(code), day) or {}
            r = bt.revenue_on(ins["rev"].get(code) or {}, day) or {}
            pe, pb = v.get("pe"), v.get("pb")
            c = [x for d, x in zip(ins["px"][sym[code]]["dates"], ins["px"][sym[code]]["close"]) if d <= day]
            if (pe and pb and pe <= 15 and pb <= 1.5 and pe * pb <= 22.5
                    and r.get("ytd_yoy") is not None and r["ytd_yoy"] >= 0 and len(c) > 252):
                cand[code] = (pe * pb, c[-22] / c[-253])
        rank_v = {c: i for i, c in enumerate(sorted(cand, key=lambda c: (-cand[c][0], c)))}
        rank_m = {c: i for i, c in enumerate(sorted(cand, key=lambda c: (cand[c][1], c)))}
        order = sorted(cand, key=lambda c: (-(rank_v[c] + rank_m[c]), cand[c][0]))
        assert gra["picks"][j] == order[:5]
        sizes.append(len(cand))
    assert max(sizes) > 5   # 至少有一天候選多於 5 檔，排名真的有作用
    for mid in ("momentum", "oneil", "tech4"):   # 不讀估值資料的方法完全不受影響
        assert g1g2["methods"][mid]["equity"] == base["methods"][mid]["equity"]
        assert g1g2["methods"][mid]["trades"] == base["methods"][mid]["trades"]


def test_baseline_is_not_affected(parts, baseline):
    b, ins, _ = parts
    again = runner.run_variant("baseline", ins, {**b, **MANIFEST}, uni=UNI)
    for mid in runner.METHOD_IDS:
        assert again["methods"][mid]["equity"] == baseline["methods"][mid]["equity"]
        assert again["methods"][mid]["trades"] == baseline["methods"][mid]["trades"]
        assert again["methods"][mid]["picks"] == baseline["methods"][mid]["picks"]
    off = runner.simulate(ins, {"graham_revenue_filter": False, "graham_value_momentum": False}, b["warmup_end"], uni=UNI)
    for mid in runner.METHOD_IDS:
        assert off["methods"][mid]["equity"] == baseline["methods"][mid]["equity"]
        assert off["methods"][mid]["trades"] == baseline["methods"][mid]["trades"]
