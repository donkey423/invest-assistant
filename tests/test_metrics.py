"""papertrade.metrics 的單元測試：手算小例子、PSR/DSR 性質、拔靴法可重現、邊界情況。"""
import math
import random
from statistics import NormalDist, mean, stdev

import pytest

from papertrade import metrics as M

N = NormalDist()


def test_daily_returns():
    assert M.daily_returns([100, 110, 99]) == pytest.approx([0.1, -0.1])
    assert M.daily_returns([]) == []
    assert M.daily_returns([100]) == []
    # 前一點 <= 0 的那筆略過
    assert M.daily_returns([0, 100, 110]) == pytest.approx([0.1])


def test_sharpe_and_volatility_manual():
    r = [0.01, -0.02, 0.03, 0.005, -0.01]
    exp = mean(r) / stdev(r) * math.sqrt(252)
    assert M.sharpe(r) == pytest.approx(exp)
    exp_rf = (mean(r) - 0.02 / 252) / stdev(r) * math.sqrt(252)
    assert M.sharpe(r, rf_annual=0.02) == pytest.approx(exp_rf)
    assert M.sharpe(r, periods=12) == pytest.approx(mean(r) / stdev(r) * math.sqrt(12))
    assert M.volatility(r) == pytest.approx(stdev(r) * math.sqrt(252))


def test_sharpe_edge_cases():
    assert M.sharpe([]) is None
    assert M.sharpe([0.01]) is None
    assert M.sharpe([0.01] * 5) is None  # 標準差為 0
    assert M.sharpe(M.daily_returns([100 * 1.01 ** k for k in range(30)])) is None  # 浮點雜訊也算 0
    assert M.volatility([]) is None
    assert M.volatility([0.01]) is None
    assert M.volatility([0.01] * 5) == pytest.approx(0.0, abs=1e-12)


def test_cagr():
    eq = [100 * 1.001 ** k for k in range(253)]  # 252 期、每期 0.1%
    assert M.cagr(eq) == pytest.approx(1.001 ** 252 - 1)
    assert M.cagr([100, 121], periods=2) == pytest.approx(0.21 + 0.21 * 0.21 + 0.21)  # 1.21² - 1
    assert M.cagr([]) is None
    assert M.cagr([100]) is None
    assert M.cagr([0, 100]) is None


def test_max_drawdown_and_calmar():
    eq = [100, 120, 90, 110, 130, 104]
    assert M.max_drawdown(eq) == pytest.approx(90 / 120 - 1)  # -25%
    assert M.max_drawdown([100, 110, 120]) == 0.0
    assert M.max_drawdown([]) == 0.0
    assert M.calmar(eq, periods=5) == pytest.approx((104 / 100 - 1) / 0.25)
    assert M.calmar([100, 110, 120]) is None  # 沒有回撤
    assert M.calmar([]) is None


def test_turnover():
    trades = [{"side": "買", "shares": 1000, "price": 50.0, "fee": 71},
              {"side": "賣", "shares": 1000, "price": 60.0, "fee": 265, "pnl": 9664}]
    eq = [100_000] * 127  # 126 期 = 半年
    # (50,000 + 60,000) / 2 / 100,000 / 0.5 年 = 1.1
    assert M.turnover(trades, eq) == pytest.approx(1.1)
    assert M.turnover([], eq) == 0.0
    assert M.turnover(trades, []) is None
    assert M.turnover(trades, [100_000]) is None
    assert M.turnover(trades, [0, 0, 0]) is None


def test_skew_kurt():
    assert M.skewness([1, 2, 3, 4, 5]) == pytest.approx(0.0)
    # [0,0,0,1]：m=0.25, m2=0.1875, m3=0.09375, m4=0.08203125
    x = [0, 0, 0, 1]
    assert M.skewness(x) == pytest.approx(0.09375 / 0.1875 ** 1.5)
    assert M.excess_kurtosis(x) == pytest.approx(0.08203125 / 0.1875 ** 2 - 3)
    assert M.excess_kurtosis([-1, 1, -1, 1]) == pytest.approx(-2.0)
    for f in (M.skewness, M.excess_kurtosis):
        assert f([]) is None
        assert f([0.01]) is None
        assert f([0.01] * 4) is None
    rng = random.Random(1)
    g = [rng.gauss(0, 1) for _ in range(20000)]
    assert abs(M.skewness(g)) < 0.1
    assert abs(M.excess_kurtosis(g)) < 0.15


def test_psr():
    assert M.probabilistic_sharpe(0.1, 250, 0.0, 3.0, sr_benchmark=0.1) == pytest.approx(0.5)
    # 手算：常態、sr=0.1、n=101 → Φ(0.1·10 / sqrt(1 + 0.5·0.01))
    assert M.probabilistic_sharpe(0.1, 101, 0.0, 3.0) == pytest.approx(N.cdf(1.0 / math.sqrt(1.005)))
    # 非常態：skew=-1、kurt=6
    exp = N.cdf(0.1 * math.sqrt(99) / math.sqrt(1 + 0.1 + 1.25 * 0.01))
    assert M.probabilistic_sharpe(0.1, 100, -1.0, 6.0) == pytest.approx(exp)
    # n 越大越有把握
    ps = [M.probabilistic_sharpe(0.05, n, -0.5, 5.0) for n in (20, 60, 250, 1000)]
    assert ps == sorted(ps) and ps[0] < ps[-1]
    # 負偏、厚尾會拉低 PSR
    assert M.probabilistic_sharpe(0.1, 250, -1.0, 8.0) < M.probabilistic_sharpe(0.1, 250, 0.0, 3.0)
    assert M.probabilistic_sharpe(0.1, 1, 0.0, 3.0) == 0.5
    assert 0.0 <= M.probabilistic_sharpe(1.0, 100, 5.0, 1.0) <= 1.0  # 分母變異項 <= 0 不出錯


def test_expected_max_sharpe():
    assert M.expected_max_sharpe(1, 0.01) == 0.0
    assert M.expected_max_sharpe(0, 0.01) == 0.0
    assert M.expected_max_sharpe(10, 0.0) == 0.0
    g = 0.5772156649015329
    for n, v in ((2, 0.01), (10, 0.0004), (100, 0.25)):
        exp = math.sqrt(v) * ((1 - g) * N.inv_cdf(1 - 1 / n) + g * N.inv_cdf(1 - 1 / (n * math.e)))
        assert M.expected_max_sharpe(n, v) == pytest.approx(exp)
    vals = [M.expected_max_sharpe(n, 0.01) for n in (1, 2, 5, 20, 100, 1000)]
    assert vals == sorted(vals) and len(set(vals)) == len(vals)
    # 文獻常見參考值：N=100、變異 1 時約 2.53
    assert M.expected_max_sharpe(100, 1.0) == pytest.approx(2.53, abs=0.01)
    assert M.expected_max_sharpe(10, 0.04) == pytest.approx(2 * M.expected_max_sharpe(10, 0.01))


def _sample_returns(seed=7, n=500, mu=0.001, sd=0.01):
    rng = random.Random(seed)
    return [rng.gauss(mu, sd) for _ in range(n)]


def test_deflated_sharpe_numeric():
    r = _sample_returns()
    out = M.deflated_sharpe(r, n_trials=20, var_trials=0.002)
    n = len(r)
    m = sum(r) / n
    sr = m / stdev(r)
    m2 = sum((x - m) ** 2 for x in r) / n
    skew = sum((x - m) ** 3 for x in r) / n / m2 ** 1.5
    kurt = sum((x - m) ** 4 for x in r) / n / m2 ** 2
    g = 0.5772156649015329
    sr0 = math.sqrt(0.002) * ((1 - g) * N.inv_cdf(1 - 1 / 20) + g * N.inv_cdf(1 - 1 / (20 * math.e)))
    dsr = N.cdf((sr - sr0) * math.sqrt(n - 1) / math.sqrt(1 - skew * sr + (kurt - 1) / 4 * sr * sr))
    assert out["sr"] == pytest.approx(sr)
    assert out["sr_annual"] == pytest.approx(sr * math.sqrt(252))
    assert out["sr_annual"] == pytest.approx(M.sharpe(r))
    assert out["sr0"] == pytest.approx(sr0)
    assert out["skew"] == pytest.approx(skew)
    assert out["kurt"] == pytest.approx(kurt)
    assert out["dsr"] == pytest.approx(dsr)
    assert out["n"] == n and out["n_trials"] == 20
    assert 0.0 <= out["dsr"] <= 1.0


def test_deflated_sharpe_properties():
    r = _sample_returns()
    ds = [M.deflated_sharpe(r, k, 0.002)["dsr"] for k in (1, 2, 10, 100, 1000)]
    assert ds == sorted(ds, reverse=True) and ds[0] > ds[-1]  # 試越多次、越難過關
    # 只試 1 次 → DSR 就是對 0 的 PSR
    one = M.deflated_sharpe(r, 1, 0.002)
    assert one["sr0"] == 0.0
    assert one["dsr"] == pytest.approx(M.probabilistic_sharpe(one["sr"], one["n"], one["skew"], one["kurt"]))
    assert M.deflated_sharpe([], 10, 0.01) is None
    assert M.deflated_sharpe([0.01], 10, 0.01) is None
    assert M.deflated_sharpe([0.01] * 10, 10, 0.01) is None


def test_summarize():
    eq = [100_000, 102_000, 99_000, 105_000, 104_000]
    trades = [{"date": "2024-01-02", "side": "買", "shares": 1000, "price": 50.0, "fee": 71},
              {"date": "2024-01-03", "side": "賣", "shares": 1000, "price": 52.0, "fee": 230, "pnl": 1699},
              {"date": "2024-01-03", "side": "買", "shares": 2000, "price": 20.0, "fee": 57},
              {"date": "2024-01-05", "side": "賣", "shares": 2000, "price": 19.0, "fee": 168, "pnl": -2225}]
    s = M.summarize(eq, trades)
    assert set(s) == {"days", "total_return", "cagr", "vol", "sharpe", "max_drawdown", "calmar",
                      "turnover", "n_trades", "fees", "win_rate"}
    r = M.daily_returns(eq)
    assert s["days"] == 5
    assert s["total_return"] == pytest.approx(0.04)
    assert s["cagr"] == pytest.approx(1.04 ** (252 / 4) - 1)
    assert s["vol"] == pytest.approx(stdev(r) * math.sqrt(252))
    assert s["sharpe"] == pytest.approx(mean(r) / stdev(r) * math.sqrt(252))
    assert s["max_drawdown"] == pytest.approx(99 / 102 - 1)
    assert s["calmar"] == pytest.approx(s["cagr"] / (1 - 99 / 102))
    assert s["turnover"] == pytest.approx((50_000 + 52_000 + 40_000 + 38_000) / 2 / 102_000 / (4 / 252))
    assert s["n_trades"] == 4
    assert s["fees"] == 526
    assert s["win_rate"] == 0.5


def test_summarize_empty():
    s = M.summarize([], [])
    assert s["days"] == 0 and s["n_trades"] == 0 and s["fees"] == 0
    assert s["max_drawdown"] == 0.0
    for k in ("total_return", "cagr", "vol", "sharpe", "calmar", "turnover", "win_rate"):
        assert s[k] is None
    s1 = M.summarize([100_000], [{"side": "買", "shares": 1, "price": 10.0, "fee": 1}])
    assert s1["win_rate"] is None and s1["fees"] == 1 and s1["sharpe"] is None


def test_bootstrap_deterministic_and_identical():
    a = _sample_returns(seed=1, n=300)
    b = _sample_returns(seed=2, n=300, mu=0.0)
    x = M.block_bootstrap_diff(a, b, n_boot=200, seed=3)
    assert x == M.block_bootstrap_diff(a, b, n_boot=200, seed=3)
    assert x != M.block_bootstrap_diff(a, b, n_boot=200, seed=4)
    assert x["diff"] == pytest.approx(M.sharpe(a) - M.sharpe(b))
    assert x["ci_low"] <= x["ci_high"]
    assert 0.0 <= x["p_gt0"] <= 1.0
    same = M.block_bootstrap_diff(a, a, n_boot=200)
    assert same["diff"] == 0.0
    assert same["ci_low"] <= 0.0 <= same["ci_high"]
    assert same["p_gt0"] == 0.0


def test_bootstrap_detects_clear_winner():
    rng = random.Random(5)
    b = [rng.gauss(0.0, 0.01) for _ in range(500)]
    a = [x + 0.002 for x in b]  # 同樣的波動、每天多賺 0.2%
    x = M.block_bootstrap_diff(a, b, n_boot=300, seed=0)
    assert x["diff"] > 0 and x["ci_low"] > 0 and x["p_gt0"] == 1.0
    y = M.block_bootstrap_diff(b, a, n_boot=300, seed=0)
    assert y["diff"] == pytest.approx(-x["diff"])
    assert y["ci_high"] < 0 and y["p_gt0"] == 0.0


def test_bootstrap_edge_cases():
    none = {"diff": None, "ci_low": None, "ci_high": None, "p_gt0": None}
    assert M.block_bootstrap_diff([], []) == none
    assert M.block_bootstrap_diff([0.01], [0.02]) == none
    assert M.block_bootstrap_diff([0.01] * 10, [0.01, -0.01] * 5) == none  # A 標準差為 0
    # 區塊比序列長、長度不同都不出錯
    out = M.block_bootstrap_diff([0.01, -0.02, 0.03, 0.0], [0.0, 0.01, -0.01, 0.02, 0.05], block=50, n_boot=50)
    assert out["diff"] is not None
