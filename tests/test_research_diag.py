"""研究框架的診斷欄位（各假設分支共用、內容相同）：每天的前幾名名單、排名內檔數、目標持股比例。只記錄，不改結果。"""
import json

import pytest

pytest.importorskip("papertrade.metrics")

from papertrade import config as C  # noqa: E402
from papertrade import engine, methods  # noqa: E402
from papertrade.research import report, runner  # noqa: E402
from tests.test_research import UNI, baseline, full, parts  # noqa: E402,F401 共用合成資料的 fixture


def test_diag_is_recorded_per_day_and_matches_the_method_ranking(parts, baseline, monkeypatch):
    b, ins, _ = parts
    seen = []
    real = methods.METHOD_FNS["graham"]

    def fn(ctx):
        out = real(ctx)
        seen.append((ctx["date"], [r["code"] for r in out]))
        return out
    monkeypatch.setitem(methods.METHOD_FNS, "graham", fn)
    sim = runner.simulate(ins, {}, b["warmup_end"], uni=UNI)
    n = len(sim["dates"])
    for mid, r in sim["methods"].items():
        assert len(r["picks"]) == len(r["candidates"]) == len(r["target"]) == n
        assert r["equity"] == baseline["methods"][mid]["equity"] and r["trades"] == baseline["methods"][mid]["trades"]
    g = sim["methods"]["graham"]
    # 第 j 筆＝評估日 dates[j] 開盤成交的那次決策（前一個交易日收盤）；最後一天收盤的決策不計
    assert len(seen) == n + 1 and seen[0][0] == b["warmup_end"] and [d for d, _ in seen[1:]] == sim["dates"]
    assert g["picks"] == [codes[:C.TOP_N] for _, codes in seen[:-1]]
    assert g["candidates"] == [len(codes) for _, codes in seen[:-1]]
    assert set(sim["methods"]["momentum"]["target"]) == {1.0} and min(sim["methods"]["combo"]["target"]) < 1.0


def test_diag_summary_in_result_and_markdown(baseline):
    for mid, m in baseline["methods"].items():
        n = len(baseline["dates"])
        assert len(m["picks"]) == len(m["target_exposure"]) == n
        t = m["all"]["target"]
        assert t["avg"] == pytest.approx(sum(m["target_exposure"]) / n, abs=1e-4) and t["min"] <= t["median"] <= 1.0
        assert sum(f["target"]["days_below_1"] for f in m["folds"]) == t["days_below_1"]
        assert sum(f["target"]["days_zero"] for f in m["folds"]) == t["days_zero"] == 0   # baseline 沒有任何方法用大盤閘門
        assert 0 <= m["all"]["avg_candidates"] <= len(UNI[0])
    assert baseline["methods"]["momentum"]["all"]["target"]["days_below_1"] == 0
    assert baseline["methods"]["combo"]["all"]["target"]["days_below_1"] > 0
    md = report.result_markdown(baseline)
    assert md.count("診斷（全期）") == len(baseline["methods"]) and "目標持股比例" in md
    json.dumps(report.copy_slim(baseline))


def test_target_stats():
    assert runner.target_stats([]) == {"avg": None, "min": None, "median": None, "days_below_1": 0, "days_zero": 0}
    assert runner.target_stats([1.0, 0.0, 0.5, 1.0]) == {"avg": 0.625, "min": 0.0, "median": 0.75, "days_below_1": 2, "days_zero": 1}


def test_picks_overlap_and_compare_diagnostics(parts, baseline, monkeypatch):
    b, ins, _ = parts
    v = {"picks": [["a", "b"], [], ["a"], []]}
    w = {"picks": [["a", "c"], ["x"], ["a"], []]}
    assert report.picks_overlap(v, w, 4) == pytest.approx((0.5 + 0 + 1) / 3)
    assert report.picks_overlap(v, w, 1) == 0.5 and report.picks_overlap(v, {}, 4) is None
    assert report.picks_overlap({"picks": [[]]}, {"picks": [[]]}, 1) is None
    monkeypatch.setitem(runner.VARIANTS, "_gate", {"methods": {"momentum": {"market_filter": 200}}})
    var = runner.run_variant("_gate", ins, {**b, "insample_sha256": "x" * 64}, uni=UNI)
    cmp = report.compare(baseline, var, [], n_boot=20)
    mom = cmp["methods"]["momentum"]
    assert mom["picks_overlap"] == 1.0   # 閘門不改排名，只改買不買
    assert mom["extra"]["base"]["target"]["days_zero"] == 0 < mom["extra"]["variant"]["target"]["days_zero"]
    assert mom["extra"]["variant"]["avg_candidates"] == mom["extra"]["base"]["avg_candidates"]
    md = report.compare_markdown(cmp)
    assert "名單重疊率 100.0%" in md and "為 0（完全不買新股）" in md and "低於年線" in md
    # 舊版結果（沒有診斷欄位）也還能比較
    old = lambda res: {**res, "methods": {mid: {**{k: x for k, x in m.items() if k not in ("picks", "target_exposure")},  # noqa: E731
                                                "all": {k: x for k, x in m["all"].items() if k not in ("avg_candidates", "target")}}
                                          for mid, m in res["methods"].items()}}
    cmp_old = report.compare(old(baseline), var, [], n_boot=20)
    assert cmp_old["methods"]["momentum"]["picks_overlap"] is None and "診斷" in report.compare_markdown(cmp_old)


def test_engine_diag_is_inert_without_the_key():
    """模擬帳戶與一般回測的 ctx 沒有 diag 鍵：decide 不會多寫任何東西。"""
    ctx = {"codes": [], "sym": {}, "px": {}, "revenue": {}, "value": {}, "chips": {}, "chip_dates": [], "chain_of": {},
           "chains": {}, "ai_watch": [], "regime": {}}
    with runner.patched_config({}):
        state = engine.new_state()
        engine.decide(state, ctx, "2024-01-02", {}, {}, {})
        assert "diag" not in ctx and all(a["pending"] == {"decided": "2024-01-02", "sells": [], "buys": []} for a in state["accounts"].values())
        ctx["diag"] = {}
        engine.decide(state, ctx, "2024-01-02", {}, {}, {})
        assert ctx["diag"]["momentum"] == {"picks": [], "candidates": 0, "target": 1.0}
