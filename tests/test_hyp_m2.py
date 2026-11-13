"""假設 M2：動能持股比例 = min(1, 擴張視窗中位數 σ ÷ 當日前 5 名等權組合近 126 日年化 σ)。合成資料。"""
import copy
from pathlib import Path
from statistics import median, stdev

import pytest

pytest.importorskip("papertrade.metrics")

from papertrade import backtest as bt  # noqa: E402
from papertrade import config as C  # noqa: E402
from papertrade import engine, methods  # noqa: E402
from papertrade.research import request, runner  # noqa: E402
from tests.test_research import UNI, baseline, full, parts  # noqa: E402,F401 共用合成資料的 fixture

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = {"insample_sha256": "x" * 64}


@pytest.fixture(scope="module")
def m2(parts):
    b, ins, _ = parts
    return runner.run_variant("M2", ins, {**b, **MANIFEST}, uni=UNI)


def _ctx(closes: dict, memo=None):
    n = len(next(iter(closes.values())))
    dates = [f"d{i:04d}" for i in range(n)]
    ctx = {"sym": {c: c for c in closes}, "px": {c: {"dates": dates, "close": list(v)} for c, v in closes.items()}}
    if memo is not None:
        ctx["memo"] = memo
    return ctx


def _walk(seed, n, step):
    out, p = [], 100.0
    for i in range(n):
        p *= 1 + step * (((i * 7 + seed * 3) % 5) - 2) / 2
        out.append(p)
    return out


def test_basket_vol_is_annualised_std_of_equal_weight_daily_returns():
    closes = {c: _walk(i, 140, 0.01 * (i + 1)) for i, c in enumerate("ABCDE")}
    ctx = _ctx(closes)
    rets = [sum(closes[c][i] / closes[c][i - 1] - 1 for c in "ABCDE") / 5 for i in range(140 - 126, 140)]
    assert len(rets) == methods.VOL_WINDOW == 126
    assert methods.basket_vol(ctx, list("ABCDE")) == pytest.approx(stdev(rets) * 252 ** 0.5)
    assert methods.basket_vol(_ctx({c: v[:126] for c, v in closes.items()}), list("ABCDE")) is None   # 126 根只有 125 筆日報酬
    assert methods.basket_vol(_ctx({c: v[:127] for c, v in closes.items()}), list("ABCDE")) is not None
    assert methods.basket_vol(ctx, []) is None
    assert methods.basket_vol(_ctx({"A": [100.0] * 140}), ["A"]) is None                               # 完全沒波動：不拿來當分母


def test_exposure_is_expanding_median_over_sigma_capped_at_one():
    closes = {c: _walk(i, 140, 0.01) for i, c in enumerate("ABCDE")}
    ranking = [{"code": c} for c in "ABCDE"]
    sigma = methods.basket_vol(_ctx(closes), list("ABCDE"))
    memo: dict = {}
    assert methods.vol_managed_exposure(_ctx(closes, memo), ranking, "2024-01-05")[0] == 1.0   # 第一個 σ̂：中位數就是它自己
    assert memo["m2_sigma"] == {"2024-01-05": sigma}
    memo = {"m2_sigma": {"2024-01-02": sigma * 0.5, "2024-01-03": sigma * 0.6, "2024-01-04": sigma * 0.4}}
    e, note = methods.vol_managed_exposure(_ctx(closes, memo), ranking, "2024-01-05")
    assert e == pytest.approx(median([0.5, 0.6, 0.4, 1.0])) == pytest.approx(0.55) and "55%" in note   # 中位數含當日
    memo = {"m2_sigma": {"2024-01-02": sigma * 3, "2024-01-03": sigma * 2}}
    assert methods.vol_managed_exposure(_ctx(closes, memo), ranking, "2024-01-05")[0] == 1.0   # 不開槓桿
    # 日期晚於決策日的紀錄不會被用到；同一天重算不會重複計入
    memo = {"m2_sigma": {"2024-01-04": sigma * 0.5, "2024-01-08": sigma * 0.01, "2024-01-09": sigma * 0.01}}
    for _ in range(2):
        assert methods.vol_managed_exposure(_ctx(closes, memo), ranking, "2024-01-05")[0] == pytest.approx(0.75)
    assert len(memo["m2_sigma"]) == 4
    # 暖機：沒有排名、或湊不滿 126 筆日報酬 → 100%，也不進中位數
    memo = {}
    assert methods.vol_managed_exposure(_ctx(closes, memo), [], "2024-01-05")[0] == 1.0
    assert methods.vol_managed_exposure(_ctx({c: v[:100] for c, v in closes.items()}, memo), ranking, "2024-01-05")[0] == 1.0
    assert not memo.get("m2_sigma")


def test_m2_run_matches_independent_recomputation_from_past_data_only(parts, baseline, m2):
    b, ins, _ = parts
    sym = UNI[0]
    cal = bt.calendar(ins["px"])
    i0 = cal.index(b["warmup_end"])
    mom = m2["methods"]["momentum"]
    hist, want = [], []
    for j, picks in enumerate(mom["picks"]):
        day = cal[i0 + j]   # 這次決策只能用到 day 為止的資料
        by_day = {}
        for code in picks:
            s = ins["px"][sym[code]]
            c = [x for d, x in zip(s["dates"], s["close"]) if d <= day]
            d = [d for d in s["dates"] if d <= day]
            for i in range(len(c) - 126, len(c)):
                by_day.setdefault(d[i], []).append(c[i] / c[i - 1] - 1)
        days = sorted(by_day)[-126:]
        if len(days) < 126:
            want.append(1.0)
            continue
        hist.append(stdev(sum(by_day[x]) / len(by_day[x]) for x in days) * 252 ** 0.5)
        want.append(min(1.0, median(hist) / hist[-1]))
    assert mom["target_exposure"] == pytest.approx(want, abs=1e-4)
    assert mom["target_exposure"][0] == 1.0 and max(mom["target_exposure"]) == 1.0
    t = mom["all"]["target"]
    assert 0 < t["days_below_1"] < len(want) and t["days_zero"] == 0 and 0 < t["min"] < 1
    assert mom["all"]["avg_exposure"] < baseline["methods"]["momentum"]["all"]["avg_exposure"]
    assert mom["picks"] == baseline["methods"]["momentum"]["picks"]   # 排名不變，只改比例
    for mid in runner.METHOD_IDS:
        if mid != "momentum":
            assert m2["methods"][mid]["equity"] == baseline["methods"][mid]["equity"]
            assert m2["methods"][mid]["trades"] == baseline["methods"][mid]["trades"]
            assert m2["methods"][mid]["target_exposure"] == baseline["methods"][mid]["target_exposure"]


def test_m2_has_no_lookahead_later_data_does_not_change_earlier_days(parts, m2):
    b, ins, _ = parts
    cal = bt.calendar(ins["px"])
    cut_day = cal[cal.index(b["warmup_end"]) + 60]
    short = copy.deepcopy(ins)
    for s in short["px"].values():
        n = sum(1 for d in s["dates"] if d <= cut_day)
        for k in s:
            s[k] = s[k][:n]
    sim = runner.simulate(short, runner.VARIANTS["M2"], b["warmup_end"], uni=UNI)
    k = len(sim["dates"])
    assert k == 60
    mom = sim["methods"]["momentum"]
    assert [round(x, 4) for x in mom["target"]] == m2["methods"]["momentum"]["target_exposure"][:k]
    assert mom["equity"] == m2["methods"]["momentum"]["equity"][:k]
    assert any(x < 1 for x in mom["target"])


def test_m2_flag_off_is_identical_to_baseline(parts, baseline):
    b, ins, _ = parts
    for flags in ({"momentum_vol_managed": False}, {"something_else": True}):
        sim = runner.simulate(ins, flags, b["warmup_end"], uni=UNI)
        for mid in runner.METHOD_IDS:
            assert sim["methods"][mid]["equity"] == baseline["methods"][mid]["equity"]
            assert sim["methods"][mid]["trades"] == baseline["methods"][mid]["trades"]
    assert runner.VARIANTS["M2"] == {"momentum_vol_managed": True}
    assert "lookback" not in runner.VARIANTS["M2"] and runner.LOOKBACK > methods.VOL_WINDOW + 1


def _decide(variant, monkeypatch, sigma_hist=None):
    """空手、前 5 名 A～E 都有 140 根 K 棒：看動能帳戶的委託金額。variant=None 表示 ctx 完全沒有 variant 鍵（模擬帳戶）。"""
    closes = {c: _walk(i, 140, 0.01) for i, c in enumerate("ABCDE")}
    ctx = _ctx(closes, {"m2_sigma": dict(sigma_hist)} if sigma_hist else {})
    for s in ctx["px"].values():
        s["open"] = list(s["close"])
    day = ctx["px"]["A"]["dates"][-1]
    ranking = [{"code": c, "score": 9 - i, "reason": "r"} for i, c in enumerate("ABCDE")]
    monkeypatch.setitem(methods.METHOD_FNS, "momentum", lambda ctx: ranking)
    ctx.update({"codes": list("ABCDE"), "revenue": {}, "value": {}, "chips": {}, "chip_dates": [], "chain_of": {}, "chains": {},
                "ai_watch": [], "regime": {"light": "紅燈", "above_ma60": True, "above_ma200": True, "vix": 15}})
    if variant is not None:
        ctx["variant"] = variant
    else:
        ctx.pop("memo")
    with runner.patched_config({}):
        state = engine.new_state()
        engine.decide(state, ctx, day, ctx["px"], ctx["sym"], {})
        return state["accounts"]["momentum"]["pending"]["buys"], next(j for j in state["journal"] if j["method"] == "momentum"), ctx


def test_m2_engine_scales_buy_amounts_and_is_inert_without_flag(monkeypatch):
    sigma = methods.basket_vol(_ctx({c: _walk(i, 140, 0.01) for i, c in enumerate("ABCDE")}), list("ABCDE"))
    low = {"d0001": sigma * 0.5, "d0002": sigma * 0.5}
    full_buys, journal, ctx = _decide(None, monkeypatch, low)
    assert [x["amount"] for x in full_buys] == [C.START_CASH // 5] * 5 and "memo" not in ctx and journal["note"] == ""
    assert _decide({}, monkeypatch, low)[0] == full_buys and _decide({"momentum_vol_managed": False}, monkeypatch, low)[0] == full_buys
    half, journal, ctx = _decide({"momentum_vol_managed": True}, monkeypatch, low)
    assert [x["amount"] for x in half] == [C.START_CASH // 10] * 5 and "持股 50%" in journal["note"]
    assert len(ctx["memo"]["m2_sigma"]) == 3


def test_m2_request_file_is_valid(monkeypatch):
    monkeypatch.chdir(ROOT)
    assert request.load_request("research/requests/102-m2.json") == [
        ["run", "--variant", "baseline", "--variant", "M2"], ["compare", "--base", "baseline", "--variant", "M2"]]
