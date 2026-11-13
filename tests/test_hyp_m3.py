"""假設 M3：動能排名改用含息報酬（還原價 adj_close 的比值），成交與計值仍用原始價。合成資料。"""
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
N = 260


@pytest.fixture(scope="module")
def m3(parts):
    b, ins, _ = parts
    return runner.run_variant("M3", ins, {**b, **MANIFEST}, uni=UNI)


def _ctx(variant=None):
    """A：價格漲 10%，期間配息 20 元（除息日價格照跌）；B：價格漲 20%、沒配息。含息報酬 A > B，不含息 B > A。"""
    dates = [f"d{i:04d}" for i in range(N)]
    a = [100.0] * 100 + [80.0] * 100 + [88.0] * (N - 200)     # 第 100 天除息 20 元，之後漲 10%
    a_adj = [80.0] * 200 + [88.0] * (N - 200)                 # 還原價：除息前的價格乘上 (1 - 20/100)
    b = [100.0] * 200 + [120.0] * (N - 200)
    px = {"A": {"dates": dates, "close": a, "adj_close": a_adj}, "B": {"dates": dates, "close": b, "adj_close": list(b)}}
    ctx = {"codes": ["A", "B"], "sym": {"A": "A", "B": "B"}, "px": px}
    if variant is not None:
        ctx["variant"] = variant
    return ctx


def test_flag_off_ranks_on_price_return_exactly_as_before():
    for variant in (None, {}, {"momentum_total_return": False}, {"other": 1}):
        out = methods.momentum(_ctx(variant))
        assert [r["code"] for r in out] == ["B", "A"]
        assert out[0]["score"] == pytest.approx(20.0) and out[1]["score"] == pytest.approx(-12.0)
        assert out[0]["reason"] == "過去 12 個月漲 +20.0%（不含最近 1 個月）"
    ctx = _ctx()
    for s in ctx["px"].values():   # 模擬帳戶的股價沒有 adj_close 欄位：照舊
        del s["adj_close"]
    assert [r["code"] for r in methods.momentum(ctx)] == ["B", "A"]


def test_flag_on_ranks_on_adjusted_close_ratio():
    out = methods.momentum(_ctx({"momentum_total_return": True}))
    assert [r["code"] for r in out] == ["B", "A"] and out[1]["score"] == pytest.approx(10.0)   # A 的含息報酬 +10%（不含息 -12%）
    ctx = _ctx({"momentum_total_return": True})
    ctx["px"]["B"]["close"] = ctx["px"]["B"]["adj_close"] = [100.0] * 200 + [105.0] * (N - 200)
    out = methods.momentum(ctx)
    assert [r["code"] for r in out] == ["A", "B"] and "含息報酬 +10.0%" in out[0]["reason"]      # 含息 A +10% 贏 B +5%
    del ctx["variant"]
    assert [r["code"] for r in methods.momentum(ctx)] == ["B", "A"]                              # 不含息 B +5% 贏 A -12%


def test_only_ratios_matter_so_later_dividends_cannot_leak():
    """還原價整條乘上常數（之後才發生的配息會造成這種位移）不改變分數。"""
    ctx = _ctx({"momentum_total_return": True})
    want = [(r["code"], r["score"]) for r in methods.momentum(ctx)]
    ctx["px"]["A"]["adj_close"] = [x * 0.37 for x in ctx["px"]["A"]["adj_close"]]
    got = [(r["code"], r["score"]) for r in methods.momentum(ctx)]
    assert [c for c, _ in got] == [c for c, _ in want] and [s for _, s in got] == pytest.approx([s for _, s in want])


def test_missing_adjusted_close_excludes_the_stock_instead_of_falling_back():
    flag = {"momentum_total_return": True}
    for breakage in ("drop", "short", "zero_start", "none_end", "negative"):
        ctx = _ctx(flag)
        s = ctx["px"]["A"]
        if breakage == "drop":
            del s["adj_close"]
        elif breakage == "short":
            s["adj_close"] = s["adj_close"][1:]
        elif breakage == "zero_start":
            s["adj_close"][-253] = 0.0
        elif breakage == "none_end":
            s["adj_close"][-22] = None
        else:
            s["adj_close"][-22] = -1.0
        assert [r["code"] for r in methods.momentum(ctx)] == ["B"], breakage
    ctx = _ctx(flag)
    ctx["px"]["A"] = {k: v[:252] for k, v in ctx["px"]["A"].items()}   # 歷史不足 253 根：和原版一樣排不進去
    assert [r["code"] for r in methods.momentum(ctx)] == ["B"]
    ctx["px"]["C"] = None
    ctx["codes"].append("C"); ctx["sym"]["C"] = "C"
    assert [r["code"] for r in methods.momentum(ctx)] == ["B"]


def test_m3_run_changes_only_momentum_and_trades_at_raw_prices(parts, baseline, m3):
    b, ins, _ = parts
    sym = UNI[0]
    for mid in runner.METHOD_IDS:
        if mid != "momentum":
            assert m3["methods"][mid]["equity"] == baseline["methods"][mid]["equity"]
            assert m3["methods"][mid]["trades"] == baseline["methods"][mid]["trades"]
            assert m3["methods"][mid]["picks"] == baseline["methods"][mid]["picks"]
    mom = m3["methods"]["momentum"]
    assert mom["picks"] != baseline["methods"]["momentum"]["picks"]   # 合成資料有配息，排名會不同
    assert mom["all"]["avg_candidates"] == baseline["methods"]["momentum"]["all"]["avg_candidates"]
    for t in mom["trades"]:   # 成交價是原始開盤價，不是還原價
        s = ins["px"][sym[t["code"]]]
        assert t["price"] == round(s["open"][s["dates"].index(t["date"])], 2)
    # 每天的名單都能只用當天以前的還原價比值重算出來
    cal = bt.calendar(ins["px"])
    i0 = cal.index(b["warmup_end"])
    for j in (0, 40, len(mom["picks"]) - 1):
        day, score = cal[i0 + j], {}
        for code, k in sym.items():
            adj = [x for d, x in zip(ins["px"][k]["dates"], ins["px"][k]["adj_close"]) if d <= day]
            if len(adj) > 252:
                score[code] = adj[-22] / adj[-253]
        assert mom["picks"][j] == sorted(score, key=score.get, reverse=True)[:5]


def test_m3_has_no_lookahead_later_data_does_not_change_earlier_days(parts, m3):
    b, ins, _ = parts
    cal = bt.calendar(ins["px"])
    cut_day = cal[cal.index(b["warmup_end"]) + 50]
    short = copy.deepcopy(ins)
    for s in short["px"].values():
        n = sum(1 for d in s["dates"] if d <= cut_day)
        for k in s:
            s[k] = s[k][:n]
    sim = runner.simulate(short, runner.VARIANTS["M3"], b["warmup_end"], uni=UNI)
    k = len(sim["dates"])
    assert k == 50 and sim["methods"]["momentum"]["picks"] == m3["methods"]["momentum"]["picks"][:k]
    assert sim["methods"]["momentum"]["equity"] == m3["methods"]["momentum"]["equity"][:k]


def test_m3_compare_reports_pick_overlap_for_the_falsification_test(baseline, m3):
    cmp = report.compare(baseline, m3, [], n_boot=20)
    mom = cmp["methods"]["momentum"]
    a, b = m3["methods"]["momentum"]["picks"], baseline["methods"]["momentum"]["picks"]
    want = sum(len(set(x) & set(y)) / 5 for x, y in zip(a, b)) / len(a)
    assert mom["picks_overlap"] == pytest.approx(want) and 0 < mom["picks_overlap"] < 1
    assert cmp["methods"]["graham"]["picks_overlap"] in (1.0, None) and not cmp["methods"]["graham"]["affected"]
    assert "名單重疊率" in report.compare_markdown(cmp)


def test_m3_variant_and_request_file(monkeypatch):
    assert runner.VARIANTS["M3"] == {"momentum_total_return": True}
    monkeypatch.chdir(ROOT)
    assert request.load_request("research/requests/103-m3.json") == [
        ["run", "--variant", "baseline", "--variant", "M3"], ["compare", "--base", "baseline", "--variant", "M3"]]
