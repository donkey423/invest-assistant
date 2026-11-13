"""回測績效指標（純標準函式庫）：報酬、夏普、回撤、週轉率、PSR／DSR、區塊拔靴法。

單位約定：
- 所有比率都是「小數」（0.12 = 12%），不四捨五入。
- `sharpe`／`volatility`／`cagr`／`turnover` 是年化值（預設一年 252 個交易日）。
- `probabilistic_sharpe`／`expected_max_sharpe`／`deflated_sharpe` 裡的 SR 是「每期（每日）」未年化的夏普，
  年化值 = 每期值 × sqrt(periods)。
"""
from __future__ import annotations

import math
import random
from statistics import NormalDist

EULER_GAMMA = 0.5772156649015329
_EPS = 1e-12  # 標準差小於這個（相對於平均的量級）就當成 0
_N = NormalDist()


# ---------- 基本工具 ----------

def _mean_std(xs: list[float]) -> tuple[float, float] | None:
    """平均與樣本標準差（ddof=1）；不足 2 筆回傳 None。"""
    n = len(xs)
    if n < 2:
        return None
    m = math.fsum(xs) / n
    var = math.fsum((x - m) ** 2 for x in xs) / (n - 1)
    return m, math.sqrt(var)


def _is_zero_std(m: float, sd: float) -> bool:
    return sd <= _EPS * max(1.0, abs(m))


def _moments(xs: list[float]) -> tuple[float, float, float] | None:
    """母體二、三、四階中心動差；變異為 0 或不足 2 筆回傳 None。"""
    n = len(xs)
    if n < 2:
        return None
    m = math.fsum(xs) / n
    m2 = math.fsum((x - m) ** 2 for x in xs) / n
    if math.sqrt(m2) <= _EPS * max(1.0, abs(m)):
        return None
    m3 = math.fsum((x - m) ** 3 for x in xs) / n
    m4 = math.fsum((x - m) ** 4 for x in xs) / n
    return m2, m3, m4


def _percentile(sorted_xs: list[float], q: float) -> float:
    """線性內插百分位，q 介於 0~1；輸入需已排序且非空。"""
    pos = q * (len(sorted_xs) - 1)
    lo = math.floor(pos)
    hi = min(lo + 1, len(sorted_xs) - 1)
    return sorted_xs[lo] + (sorted_xs[hi] - sorted_xs[lo]) * (pos - lo)


# ---------- 報酬與風險 ----------

def daily_returns(equity: list[float]) -> list[float]:
    """相鄰兩點的簡單報酬。前一點淨值 <= 0 時無法計算，該筆略過。"""
    out = []
    for a, b in zip(equity, equity[1:]):
        if a is None or b is None or a <= 0:
            continue
        out.append(b / a - 1)
    return out


def sharpe(returns: list[float], rf_annual: float = 0.0, periods: int = 252) -> float | None:
    """年化夏普：(平均報酬 - 每期無風險利率) / 樣本標準差 × sqrt(periods)。不足 2 筆或標準差為 0 回傳 None。"""
    ms = _mean_std(returns)
    if ms is None or periods <= 0:
        return None
    m, sd = ms
    if _is_zero_std(m, sd):
        return None
    return (m - rf_annual / periods) / sd * math.sqrt(periods)


def volatility(returns: list[float], periods: int = 252) -> float | None:
    """年化波動率（樣本標準差 × sqrt(periods)）；不足 2 筆回傳 None。"""
    ms = _mean_std(returns)
    if ms is None or periods <= 0:
        return None
    return ms[1] * math.sqrt(periods)


def cagr(equity: list[float], periods: int = 252) -> float | None:
    """年化報酬：(期末/期初)^(periods/(n-1)) - 1。不足 2 點、期初 <= 0 或期末 < 0 回傳 None。"""
    n = len(equity)
    if n < 2 or periods <= 0 or equity[0] <= 0 or equity[-1] < 0:
        return None
    return (equity[-1] / equity[0]) ** (periods / (n - 1)) - 1


def max_drawdown(equity: list[float]) -> float:
    """最大回撤：從前高到谷底最深的跌幅（<= 0 的小數）。空的或沒跌過回傳 0.0。"""
    peak, worst = None, 0.0
    for v in equity:
        if peak is None or v > peak:
            peak = v
        if peak is not None and peak > 0:
            worst = min(worst, v / peak - 1)
    return worst


def calmar(equity: list[float], periods: int = 252) -> float | None:
    """Calmar = 年化報酬 / |最大回撤|；沒有回撤或算不出年化報酬回傳 None。"""
    g, dd = cagr(equity, periods), max_drawdown(equity)
    if g is None or dd == 0:
        return None
    return g / abs(dd)


def turnover(trades: list[dict], equity: list[float], periods: int = 252) -> float | None:
    """年化單邊週轉率 = (買進金額 + 賣出金額) / 2 / 平均淨值 / 年數。

    金額 = 股數 × 成交價；年數 = (len(equity)-1)/periods。資料不足或平均淨值 <= 0 回傳 None。
    """
    if len(equity) < 2 or periods <= 0:
        return None
    years = (len(equity) - 1) / periods
    avg = math.fsum(equity) / len(equity)
    if avg <= 0:
        return None
    notional = math.fsum((t.get("shares") or 0) * (t.get("price") or 0) for t in trades or [])
    return notional / 2 / avg / years


# ---------- 高階動差 ----------

def skewness(returns: list[float]) -> float | None:
    """偏態（母體動差 m3 / m2^1.5）；不足 2 筆或變異為 0 回傳 None。"""
    mm = _moments(returns)
    if mm is None:
        return None
    m2, m3, _ = mm
    return m3 / m2 ** 1.5


def excess_kurtosis(returns: list[float]) -> float | None:
    """超額峰態（m4 / m2² - 3，常態分配為 0）；不足 2 筆或變異為 0 回傳 None。"""
    mm = _moments(returns)
    if mm is None:
        return None
    m2, _, m4 = mm
    return m4 / m2 ** 2 - 3


# ---------- PSR / DSR ----------

def probabilistic_sharpe(sr: float, n: int, skew: float, kurt: float, sr_benchmark: float = 0.0) -> float:
    """PSR（Bailey & López de Prado 2012）：真實夏普高於門檻 sr_benchmark 的機率。

    注意：sr 與 sr_benchmark 都是「每期、未年化」的夏普；kurt 是一般峰態（常態 = 3，不是超額峰態）。
    PSR = Φ( (sr - sr*)·sqrt(n-1) / sqrt(1 - skew·sr + (kurt-1)/4·sr²) )
    n < 2 時沒有資訊，回傳 0.5；分母的變異項 <= 0（極端偏態）時以極小正數代替。
    """
    if n < 2:
        return 0.5
    var = 1 - skew * sr + (kurt - 1) / 4 * sr * sr
    if var <= 0:
        var = _EPS
    return _N.cdf((sr - sr_benchmark) * math.sqrt(n - 1) / math.sqrt(var))


def expected_max_sharpe(n_trials: int, var_trials: float) -> float:
    """虛無假設（真實夏普皆為 0）下，N 個獨立試驗中最大夏普的期望值（Bailey & López de Prado 2014）。

    sqrt(var_trials)·[ (1-γ)·Φ⁻¹(1 - 1/N) + γ·Φ⁻¹(1 - 1/(N·e)) ]，γ 為歐拉常數。
    var_trials 是各試驗「每期夏普」的變異數，所以回傳值也是每期夏普。N <= 1 或變異 <= 0 回傳 0.0。
    """
    if n_trials is None or n_trials <= 1 or var_trials is None or var_trials <= 0:
        return 0.0
    a = _N.inv_cdf(1 - 1 / n_trials)
    b = _N.inv_cdf(1 - 1 / (n_trials * math.e))
    return math.sqrt(var_trials) * ((1 - EULER_GAMMA) * a + EULER_GAMMA * b)


def deflated_sharpe(returns: list[float], n_trials: int, var_trials: float, periods: int = 252) -> dict | None:
    """DSR（Deflated Sharpe Ratio）：把「試了很多組參數挑最好的」這件事扣掉之後的夏普顯著性。

    dsr 是 0~1 的機率：這個策略的真實夏普，高於「n_trials 個純隨機策略裡最好那個會表現出來的夏普」的機率。
    一般以 dsr > 0.95 當作過關門檻；低於它代表這個夏普很可能只是多次嘗試挑出來的運氣。

    - returns：每期（每日）報酬。
    - n_trials：總共試過幾組策略／參數。
    - var_trials：所有試驗「每期夏普」的變異數（不是年化夏普的變異數）。
    回傳 {"sr": 每期夏普, "sr_annual": sr×sqrt(periods), "sr0": 門檻（每期）, "dsr", "n", "skew", "kurt"（一般峰態）, "n_trials"}；
    報酬不足 2 筆或標準差為 0 回傳 None。無風險利率視為 0。
    """
    ms = _mean_std(returns)
    if ms is None or _is_zero_std(*ms):
        return None
    sr = ms[0] / ms[1]
    n = len(returns)
    skew = skewness(returns) or 0.0
    ek = excess_kurtosis(returns)
    kurt = (ek if ek is not None else 0.0) + 3
    sr0 = expected_max_sharpe(n_trials, var_trials)
    return {"sr": sr, "sr_annual": sr * math.sqrt(periods), "sr0": sr0,
            "dsr": probabilistic_sharpe(sr, n, skew, kurt, sr0),
            "n": n, "skew": skew, "kurt": kurt, "n_trials": n_trials}


# ---------- 總表 ----------

def summarize(equity: list[float], trades: list[dict], rf_annual: float = 0.0, periods: int = 252) -> dict:
    """把一條淨值曲線和交易紀錄整理成一張績效表（全部是未四捨五入的小數）。

    win_rate 是賣出交易中 pnl > 0 的比例，僅供參考（沒有賣出回傳 None）。
    """
    equity = list(equity or [])
    trades = list(trades or [])
    rets = daily_returns(equity)
    sells = [t for t in trades if t.get("side") == "賣"]
    total = equity[-1] / equity[0] - 1 if len(equity) >= 2 and equity[0] > 0 else None
    return {
        "days": len(equity),
        "total_return": total,
        "cagr": cagr(equity, periods),
        "vol": volatility(rets, periods),
        "sharpe": sharpe(rets, rf_annual, periods),
        "max_drawdown": max_drawdown(equity),
        "calmar": calmar(equity, periods),
        "turnover": turnover(trades, equity, periods),
        "n_trades": len(trades),
        "fees": math.fsum(t.get("fee") or 0 for t in trades),
        "win_rate": sum((t.get("pnl") or 0) > 0 for t in sells) / len(sells) if sells else None,
    }


# ---------- 區塊拔靴法 ----------

def block_bootstrap_diff(returns_a: list[float], returns_b: list[float], block: int = 21,
                         n_boot: int = 2000, seed: int = 0) -> dict:
    """成對環狀區塊拔靴法：A 與 B 兩條日報酬的「年化夏普差（A - B）」信賴區間。

    兩條序列用同一組抽出的區塊（保留同日配對與自我相關）；長度不同時只取前面共同的長度。
    回傳 {"diff": 實際差, "ci_low": 2.5 百分位, "ci_high": 97.5 百分位, "p_gt0": 拔靴差 > 0 的比例}；
    算不出來（資料不足、標準差為 0）時各值為 None。固定 seed 結果可重現。
    """
    n = min(len(returns_a), len(returns_b))
    a, b = list(returns_a[:n]), list(returns_b[:n])
    none = {"diff": None, "ci_low": None, "ci_high": None, "p_gt0": None}
    sa, sb = sharpe(a), sharpe(b)
    if sa is None or sb is None or n_boot <= 0:
        return none
    block = max(1, min(int(block), n))
    rng = random.Random(seed)
    n_blocks = -(-n // block)
    diffs = []
    for _ in range(n_boot):
        idx = []
        for _ in range(n_blocks):
            s = rng.randrange(n)
            idx.extend((s + k) % n for k in range(block))
        idx = idx[:n]
        ra, rb = sharpe([a[i] for i in idx]), sharpe([b[i] for i in idx])
        if ra is None or rb is None:
            continue
        diffs.append(ra - rb)
    if not diffs:
        return {**none, "diff": sa - sb}
    diffs.sort()
    return {"diff": sa - sb, "ci_low": _percentile(diffs, 0.025), "ci_high": _percentile(diffs, 0.975),
            "p_gt0": sum(d > 0 for d in diffs) / len(diffs)}
