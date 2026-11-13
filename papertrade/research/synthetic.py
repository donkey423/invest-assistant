"""合成資料集：給測試與本機試跑用（沒有網路也能把 fetch → run → compare 走一遍）。數字沒有任何投資意義。"""
from __future__ import annotations

import math
import random
from datetime import date, timedelta

from ..__main__ import universe


def weekdays(start: str, n: int) -> list[str]:
    d, out = date.fromisoformat(start), []
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += timedelta(days=1)
    return out


def _series(rnd: random.Random, days: list[str], drift: float, vol: float, dividend: float = 0.0, start: float = 100.0,
            div_month: str = "07") -> dict:
    """隨機漫步日線；dividend > 0 時每年 div_month 月第一個交易日除息（約當殖利率 dividend）。"""
    p, o, c, v, div, seen = start, [], [], [], [], set()
    for d in days:
        pay = 0.0
        if dividend and d[5:7] == div_month and d[:4] not in seen:
            seen.add(d[:4])
            pay = round(p * dividend, 2)
            p -= pay
        op = p * math.exp(rnd.gauss(0, vol / 3))
        p = op * math.exp(rnd.gauss(drift, vol))
        o.append(round(op, 2))
        c.append(round(p, 2))
        v.append(int(rnd.uniform(5e5, 2e6) * (3 if rnd.random() < 0.05 else 1)))
        div.append(pay)
    adj, k = [0.0] * len(c), 1.0
    for i in range(len(c) - 1, -1, -1):   # 仿 Yahoo：往回乘上之後每次配息的係數
        adj[i] = round(c[i] * k, 4)
        if div[i] and i:
            k *= 1 - div[i] / c[i - 1]
    return {"dates": list(days), "open": o, "close": c, "volume": v, "div": div, "adj_close": adj, "split": [0.0] * len(c)}


def make_dataset(n_days: int = 2160, codes: list[str] | None = None, seed: int = 0, start: str = "2018-01-02",
                 div_month: str = "07") -> dict:
    """完整（還沒切保留段）的合成資料集。codes 省略時用整個選股池。"""
    sym = universe()[0]
    codes = list(sym) if codes is None else codes
    days = weekdays(start, n_days)
    px, rev, val, chips = {}, {}, {}, {d: {} for d in days}
    mkt = random.Random(f"{seed}-mkt")
    px["^TWII"] = _series(mkt, days, 0.0003, 0.011, start=10000.0)
    px["0050.TW"] = _series(mkt, days, 0.0003, 0.011, dividend=0.03, start=80.0, div_month=div_month)
    vix = _series(mkt, days, 0.0, 0.06, start=18.0)
    vix["close"] = [round(min(60.0, max(10.0, 18 + (x - 18) * 0.2)), 2) for x in vix["close"]]
    px["^VIX"] = vix
    for code in codes:
        rnd = random.Random(f"{seed}-{code}")
        s = _series(rnd, days, rnd.uniform(-0.0003, 0.0009), rnd.uniform(0.012, 0.03), dividend=rnd.choice([0, 0.02, 0.04, 0.06]),
                    div_month=div_month)
        px[sym[code]] = s
        base, growth, series = rnd.uniform(500, 5000), rnd.uniform(-0.1, 0.3), {}
        y0, y1 = int(days[0][:4]) - 1, int(days[-1][:4])
        for y in range(y0, y1 + 1):
            for m in range(1, 13):
                series[f"{y:04d}-{m:02d}"] = round(base * (1 + growth) ** (y - y0) * rnd.uniform(0.8, 1.2), 2)
        rev[code] = series
        pe, pb, col = rnd.uniform(6, 25), rnd.uniform(0.6, 3), {"dates": list(days), "pe": [], "pb": [], "dy": []}
        for _ in days:
            pe = min(60, max(4, pe * math.exp(rnd.gauss(0, 0.01))))
            pb = min(8, max(0.4, pb * math.exp(rnd.gauss(0, 0.01))))
            col["pe"].append(round(pe, 2))
            col["pb"].append(round(pb, 2))
            col["dy"].append(round(rnd.uniform(0, 7), 2))
        val[code] = col
        if sym[code].endswith(".TW"):   # 上櫃股沒有 T86
            num = sym[code].split(".")[0]
            for d in days:
                chips[d][num] = {"foreign": rnd.randint(-900000, 900000), "trust": rnd.randint(-200000, 300000)}
    return {"px": px, "rev": rev, "val": val, "chips": chips}


def sub_universe(codes: list[str]):
    """只含指定代號的選股池（測試用）。"""
    sym, names, chain_of = universe()
    return ({c: sym[c] for c in codes}, {c: names[c] for c in codes}, {c: chain_of.get(c, []) for c in codes})

