"""假設 G2：通過葛拉漢門檻後，排名改為 0.5×百分位(-pe×pb) + 0.5×百分位(12-1 報酬)；算不出動能的排除。合成資料。"""
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
FLAG = {"graham_value_momentum": True}
N = 260


@pytest.fixture(scope="module")
def cheap(parts):
    """共用的合成資料只有三四檔過得了葛拉漢門檻（全部買進，排名不影響結果）；把本益比與淨值比壓低，讓候選多於 5 檔。"""
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
def g2(cheap):
    b, ins = cheap
    return runner.run_variant("G2", ins, {**b, **MANIFEST}, uni=UNI)


def _series(mom_pct, n=N):
    """c[-253] = 100、c[-22] = 100×(1+mom)；最近 21 天再大漲一倍（12-1 不該看到）。"""
    c = [100.0] * (n - 100) + [100.0 * (1 + mom_pct / 100)] * 79 + [500.0] * 21
    return {"dates": [f"d{i:04d}" for i in range(n)], "close": c}


def _ctx(variant=None, moms=None):
    #            葛拉漢數   12-1 報酬
    # A  8×0.8  = 6.4      +30%
    # B 10×1.0  = 10.0     +50%
    # C 12×1.2  = 14.4     -10%
    # D  6×0.5  = 3.0      -20%
    # E  9×0.9  = 8.1      （歷史不足，算不出動能）
    # X 20×1.0  沒過門檻    +90%
    value = {"A": {"pe": 8.0, "pb": 0.8}, "B": {"pe": 10.0, "pb": 1.0}, "C": {"pe": 12.0, "pb": 1.2},
             "D": {"pe": 6.0, "pb": 0.5}, "E": {"pe": 9.0, "pb": 0.9}, "X": {"pe": 20.0, "pb": 1.0}}
    moms = moms or {"A": 30, "B": 50, "C": -10, "D": -20, "X": 90}
    px = {c: _series(m) for c, m in moms.items()}
    px["E"] = _series(40, n=252)
    ctx = {"codes": list(value), "sym": {c: c for c in value}, "value": value, "px": px, "revenue": {}}
    if variant is not None:
        ctx["variant"] = variant
    return ctx


def test_flag_off_is_the_original_graham():
    want = None
    for variant in (None, {}, {"graham_value_momentum": False}, {"other": True}):
        out = methods.graham(_ctx(variant))
        assert [r["code"] for r in out] == ["D", "A", "E", "B", "C"]
        assert out[0] == {"code": "D", "score": -3.0, "reason": "本益比 6.0、股價淨值比 0.50，葛拉漢數 3.0（≤ 22.5）"}
        want = want or out
        assert out == want
    ctx = _ctx()
    del ctx["px"], ctx["sym"]   # 原版完全不讀股價
    assert methods.graham(ctx) == want


def test_flag_on_blends_value_and_momentum_percentiles_half_half():
    out = methods.graham(_ctx(FLAG))
    # 候選＝A、B、C、D（E 算不出動能、X 沒過門檻，都不在百分位的母體裡）
    # 價值百分位：D 1、A 2/3、B 1/3、C 0；動能百分位：B 1、A 2/3、C 1/3、D 0
    score = {r["code"]: r["score"] for r in out}
    assert score == pytest.approx({"A": 2 / 3, "B": 2 / 3, "D": 0.5, "C": 1 / 6})
    assert [r["code"] for r in out] == ["A", "B", "D", "C"]   # A、B 同分：葛拉漢數低的 A 在前
    assert score["A"] == score["B"]                            # 數學上相等的分數確實相等（不受浮點誤差影響）
    assert "過去 12 個月 +30.0%（不含最近 1 個月）" in out[0]["reason"] and "價值百分位 67、動能百分位 67，各半" in out[0]["reason"]
    assert methods.ret(_ctx(), "A", 252, skip=21) == pytest.approx(30.0)   # 用的是 12-1：沒有吃到最近 21 天的大漲


def test_ties_fall_back_to_graham_number_whatever_the_universe_order():
    for order in (["A", "B", "C", "D", "E", "X"], ["X", "E", "D", "C", "B", "A"], ["B", "D", "A", "C", "X", "E"]):
        ctx = _ctx(FLAG)
        ctx["codes"] = order
        assert [r["code"] for r in methods.graham(ctx)] == ["A", "B", "D", "C"]
    # 三檔、價值與動能完全相反：三檔同分，照葛拉漢數由低到高
    ctx = _ctx(FLAG, {"A": 0, "B": 50, "C": 80, "D": -30, "X": 0})
    ctx["codes"] = ["C", "B", "A"]
    out = methods.graham(ctx)
    assert [r["score"] for r in out] == [0.5, 0.5, 0.5] and [r["code"] for r in out] == ["A", "B", "C"]


def test_small_pools():
    ctx = _ctx(FLAG)
    ctx["codes"] = ["B", "E", "X"]
    out = methods.graham(ctx)
    assert [(r["code"], r["score"]) for r in out] == [("B", 0.5)]   # 只剩一檔：兩個百分位都是 0.5
    ctx["codes"] = ["E", "X"]
    assert methods.graham(ctx) == []
    ctx = _ctx(FLAG)
    ctx["px"]["C"] = None                                           # 抓不到股價：算不出動能，排除
    assert [r["code"] for r in methods.graham(ctx)] == ["D", "A", "B"]   # 三檔價值與動能完全相反、全部同分：照葛拉漢數


def test_g2_run_reranks_inside_the_same_gates(cheap, base, g2):
    b, ins = cheap
    sym = UNI[0]
    cal = bt.calendar(ins["px"])
    i0 = cal.index(b["warmup_end"])
    gra, old = g2["methods"]["graham"], base["methods"]["graham"]
    assert gra["picks"] != old["picks"] and gra["equity"] != old["equity"]
    assert 5 < gra["all"]["avg_candidates"] <= old["all"]["avg_candidates"]   # 門檻不變，只會因為算不出動能而變少
    for j in (0, 30, len(gra["picks"]) - 1):   # 用到 day 為止的原始資料重算名單
        day, cand = cal[i0 + j], {}
        for code in sym:
            v = runner.value_at(ins["val"].get(code), day) or {}
            pe, pb = v.get("pe"), v.get("pb")
            c = [x for d, x in zip(ins["px"][sym[code]]["dates"], ins["px"][sym[code]]["close"]) if d <= day]
            if pe and pb and pe <= 15 and pb <= 1.5 and pe * pb <= 22.5 and len(c) > 252:
                cand[code] = (pe * pb, c[-22] / c[-253])
        n = len(cand)
        rank_v = {c: i for i, c in enumerate(sorted(cand, key=lambda c: (-cand[c][0], c)))}
        rank_m = {c: i for i, c in enumerate(sorted(cand, key=lambda c: (cand[c][1], c)))}
        order = sorted(cand, key=lambda c: (-(rank_v[c] + rank_m[c]), cand[c][0]))
        assert n > 5 and gra["picks"][j] == order[:5]
    for mid in ("momentum", "oneil", "tech4"):   # 不讀估值資料的方法完全不受影響
        assert g2["methods"][mid]["equity"] == base["methods"][mid]["equity"]
        assert g2["methods"][mid]["trades"] == base["methods"][mid]["trades"]


def test_g2_on_shared_dataset_touches_only_graham(parts, baseline):
    b, ins, _ = parts
    res = runner.run_variant("G2", ins, {**b, **MANIFEST}, uni=UNI)
    for mid in runner.METHOD_IDS:
        if mid != "graham":
            assert res["methods"][mid]["equity"] == baseline["methods"][mid]["equity"]
            assert res["methods"][mid]["trades"] == baseline["methods"][mid]["trades"]
    for flags in ({"graham_value_momentum": False}, {"other": True}):
        sim = runner.simulate(ins, flags, b["warmup_end"], uni=UNI)
        assert sim["methods"]["graham"]["equity"] == baseline["methods"]["graham"]["equity"]
        assert sim["methods"]["graham"]["trades"] == baseline["methods"]["graham"]["trades"]


def test_g2_has_no_lookahead_later_data_does_not_change_earlier_days(cheap, g2):
    b, ins = cheap
    cal = bt.calendar(ins["px"])
    cut_day = cal[cal.index(b["warmup_end"]) + 50]
    short = copy.deepcopy(ins)
    for s in short["px"].values():
        n = sum(1 for d in s["dates"] if d <= cut_day)
        for k in s:
            s[k] = s[k][:n]
    for col in short["val"].values():
        n = sum(1 for d in col["dates"] if d <= cut_day)
        for k in col:
            col[k] = col[k][:n]
    sim = runner.simulate(short, runner.VARIANTS["G2"], b["warmup_end"], uni=UNI)
    k = len(sim["dates"])
    assert k == 50 and sim["methods"]["graham"]["picks"] == g2["methods"]["graham"]["picks"][:k]
    assert sim["methods"]["graham"]["equity"] == g2["methods"]["graham"]["equity"][:k]


def test_g2_compare_reports_candidates_and_positions(base, g2):
    cmp = report.compare(base, g2, [], n_boot=20)
    gra = cmp["methods"]["graham"]
    assert gra["affected"] and [m for m, x in cmp["methods"].items() if x["affected"]] == ["graham"]
    assert gra["extra"]["variant"]["avg_candidates"] is not None and 0 < gra["picks_overlap"] < 1
    md = report.compare_markdown(cmp)
    assert "平均持股檔數" in md and "年換手" in md and "排名內的檔數（通過門檻的檔數）平均" in md


def test_g2_variant_and_request_file(monkeypatch):
    assert runner.VARIANTS["G2"] == FLAG and "G1G2" not in runner.VARIANTS
    monkeypatch.chdir(ROOT)
    assert request.load_request("research/requests/105-g2.json") == [
        ["run", "--variant", "baseline", "--variant", "G2"], ["compare", "--base", "baseline", "--variant", "G2"]]
