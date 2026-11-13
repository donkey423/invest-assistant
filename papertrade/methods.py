"""各種選股方法。每個函式收到同一份 ctx，回傳排好名次的清單 [{code, score, reason}]。

ctx 的資料都只到「決策日」收盤為止，不會偷看到之後的價格。
"""
from __future__ import annotations


def _closes(ctx, code):
    s = ctx["px"].get(ctx["sym"][code])
    return s["close"] if s else []


def ret(ctx, code, n, skip=0):
    """近 n 個交易日（扣掉最近 skip 天）的報酬率 %。"""
    c = _closes(ctx, code)
    if len(c) <= n:
        return None
    a, b = c[-1 - n], c[-1 - skip]
    return (b / a - 1) * 100 if a else None


def ma(ctx, code, n):
    c = _closes(ctx, code)
    return sum(c[-n:]) / n if len(c) >= n else None


def _rank(items, key, reverse=True):
    items = [i for i in items if i["score"] is not None]
    return sorted(items, key=key or (lambda i: i["score"]), reverse=reverse)


def ret_adj(ctx, code, n, skip=0):
    """ret() 的含息版：用還原價 adj_close 的比值（還原價的水準沒有意義，只能用比值）。

    沒有還原價（缺欄位、和收盤價筆數對不上、端點缺值或不是正數）一律回傳 None，不退回用原始收盤價：
    混用兩種報酬會讓配息多的股票在排名裡吃虧，寧可不排。
    """
    s = ctx["px"].get(ctx["sym"][code]) or {}
    c = s.get("adj_close")
    if not c or len(c) != len(s.get("close") or []) or len(c) <= n:
        return None
    a, b = c[-1 - n], c[-1 - skip]
    if not a or not b or a <= 0 or b <= 0:
        return None
    return (b / a - 1) * 100


def momentum(ctx):
    total = (ctx.get("variant") or {}).get("momentum_total_return")  # 假設 M3：只有研究框架會帶這個旗標
    out = []
    for code in ctx["codes"]:
        r = ret_adj(ctx, code, 252, skip=21) if total else ret(ctx, code, 252, skip=21)
        if r is not None:
            out.append({"code": code, "score": r,
                        "reason": f"過去 12 個月{'含息報酬' if total else '漲'} {r:+.1f}%（不含最近 1 個月）"})
    return _rank(out, None)


def reversal(ctx):
    out = []
    for code in ctx["codes"]:
        r = ret(ctx, code, 21)
        rev = ctx["revenue"].get(code) or {}
        if r is None or rev.get("yoy") is None or rev["yoy"] <= 0:
            continue
        out.append({"code": code, "score": -r,
                    "reason": f"近 1 個月 {r:+.1f}%，但 {rev.get('ym', '')} 營收年增 {rev['yoy']:+.1f}%"})
    return _rank(out, None)


def revenue(ctx):
    out = []
    for code in ctx["codes"]:
        rev = ctx["revenue"].get(code) or {}
        yoy, ytd = rev.get("yoy"), rev.get("ytd_yoy")
        if yoy is None or ytd is None or yoy <= 0 or yoy <= ytd:
            continue
        out.append({"code": code, "score": yoy - ytd,
                    "reason": f"{rev.get('ym', '')} 營收年增 {yoy:+.1f}%，比今年累計 {ytd:+.1f}% 加速 {yoy - ytd:.1f} 個百分點"})
    return _rank(out, None)


def _flow(ctx, code, who, days):
    """近 days 個交易日的法人買賣超金額（億元，用決策日收盤價估算）。"""
    c = _closes(ctx, code)
    if not c:
        return None, 0
    total, seen, pos = 0.0, 0, 0
    for d in ctx["chip_dates"][-days:]:
        row = (ctx["chips"].get(d) or {}).get(code)
        if row is None:
            continue
        seen += 1
        total += row[who]
        pos += row[who] > 0
    if not seen:
        return None, 0
    return total * c[-1] / 1e8, pos


def trust(ctx):
    out = []
    for code in ctx["codes"]:
        v, _ = _flow(ctx, code, "trust", 1)
        if v is not None and v > 0:
            out.append({"code": code, "score": v, "reason": f"{ctx['chip_dates'][-1]} 投信買超約 {v:.2f} 億元"})
    return _rank(out, None)


def foreign(ctx):
    out = []
    for code in ctx["codes"]:
        v, pos = _flow(ctx, code, "foreign", 5)
        m = ma(ctx, code, 20)
        c = _closes(ctx, code)
        if v is None or v <= 0 or m is None or c[-1] < m:
            continue
        out.append({"code": code, "score": v,
                    "reason": f"外資近 5 日買超約 {v:.2f} 億元（{pos} 天買超），股價在 20 日均線之上"})
    return _rank(out, None)


def _pct_rank(values: dict, higher_better=True) -> dict:
    """{code: 值} → {code: 0~1 百分位}，1 最好。"""
    xs = sorted((v, k) for k, v in values.items() if v is not None)
    n = len(xs)
    if n < 2:
        return {k: 0.5 for _, k in xs}
    out = {k: i / (n - 1) for i, (_, k) in enumerate(xs)}
    return out if higher_better else {k: 1 - v for k, v in out.items()}


def value(ctx):
    cand = {}
    for code in ctx["codes"]:
        v = ctx["value"].get(code) or {}
        r3 = ret(ctx, code, 63)
        if not v.get("yield") or v["yield"] < 3.5 or r3 is None or r3 < 0:
            continue
        if v.get("pe") is not None and v["pe"] <= 0:
            continue
        cand[code] = v
    pe = _pct_rank({k: v.get("pe") for k, v in cand.items()}, higher_better=False)
    dy = _pct_rank({k: v.get("yield") for k, v in cand.items()})
    pb = _pct_rank({k: v.get("pb") for k, v in cand.items()}, higher_better=False)
    out = []
    for code, v in cand.items():
        parts = [x[code] for x in (pe, dy, pb) if code in x]
        if not parts:
            continue
        pe_txt = f"本益比 {v['pe']:.1f}、" if v.get("pe") else ""
        pb_txt = f"、股價淨值比 {v['pb']:.2f}" if v.get("pb") else ""
        out.append({"code": code, "score": sum(parts) / len(parts),
                    "reason": f"{pe_txt}殖利率 {v['yield']:.2f}%{pb_txt}，近 3 個月 {ret(ctx, code, 63):+.1f}%"})
    return _rank(out, None)


def chain(ctx):
    best = {}
    for code in ctx["codes"]:
        for cid in ctx["chain_of"].get(code, []):
            ch = ctx["chains"].get(cid) or {}
            if ch.get("light") != "轉強":
                continue
            yoy = (ctx["revenue"].get(code) or {}).get("yoy")
            if yoy is None:
                continue
            cur = best.get(cid)
            if cur is None or yoy > cur["score"]:
                best[cid] = {"code": code, "score": yoy,
                             "reason": f"「{ch.get('name', cid)}」鏈燈號轉強（{'、'.join(ch.get('why') or [])[:60]}），營收年增 {yoy:+.1f}%"}
    seen, out = set(), []
    for item in sorted(best.values(), key=lambda i: i["score"], reverse=True):
        if item["code"] not in seen:
            seen.add(item["code"])
            out.append(item)
    return out


def ai_theme(ctx):
    out, n = [], len(ctx["ai_watch"])
    for i, w in enumerate(ctx["ai_watch"]):
        if w["code"] in ctx["sym"]:
            out.append({"code": w["code"], "score": n - i, "reason": f"AI 主題推理（{w['date']}）：{w['title']}"})
    return out


def combo(ctx):
    comps = {
        "動能": _pct_rank({c: ret(ctx, c, 63) for c in ctx["codes"]}),
        "營收": _pct_rank({c: ((ctx["revenue"].get(c) or {}).get("yoy") or 0) - ((ctx["revenue"].get(c) or {}).get("ytd_yoy") or 0)
                         if (ctx["revenue"].get(c) or {}).get("yoy") is not None else None for c in ctx["codes"]}),
        "外資": _pct_rank({c: _flow(ctx, c, "foreign", 5)[0] for c in ctx["codes"]}),
        "價值": _pct_rank({c: (ctx["value"].get(c) or {}).get("yield") for c in ctx["codes"]}),
        "產業鏈": _pct_rank({c: max([{"轉強": 1, "持平": 0, "轉弱": -1}.get((ctx["chains"].get(i) or {}).get("light"), 0)
                                   for i in ctx["chain_of"].get(c, [])] or [0]) for c in ctx["codes"]}),
    }
    out = []
    for code in ctx["codes"]:
        got = {k: v[code] for k, v in comps.items() if code in v}
        if len(got) < 3:
            continue
        top = sorted(got.items(), key=lambda kv: kv[1], reverse=True)[:2]
        out.append({"code": code, "score": sum(got.values()) / len(got),
                    "reason": f"綜合分數 {sum(got.values()) / len(got) * 100:.0f}（{len(got)} 項，強項：{'、'.join(f'{k} {v * 100:.0f}' for k, v in top)}）"})
    return _rank(out, None)


def exposure(regime: dict) -> tuple[float, str]:
    """綜合帳戶的持股比例：景氣燈號＋大盤是否在季線之上＋VIX。"""
    light, above, vix = regime.get("light"), regime.get("above_ma60"), regime.get("vix")
    level = {"紅燈": 1.0, "黃紅燈": 1.0, "綠燈": 0.9, "黃藍燈": 0.8, "藍燈": 1.0}.get(light, 0.9)
    why = [f"景氣{light or '未知'}"]
    if above is False:
        level -= 0.3
        why.append("大盤跌破季線")
    if vix is not None and vix >= 25:
        level -= 0.2
        why.append(f"VIX {vix:.0f} 偏高")
    level = max(0.3, min(1.0, level))
    return level, "、".join(why) + f" → 持股 {level * 100:.0f}%"


def graham(ctx):
    out = []
    for code in ctx["codes"]:
        v = ctx["value"].get(code) or {}
        pe, pb = v.get("pe"), v.get("pb")
        if not pe or not pb or pe <= 0 or pb <= 0 or pe > 15 or pb > 1.5 or pe * pb > 22.5:
            continue
        out.append({"code": code, "score": -pe * pb,
                    "reason": f"本益比 {pe:.1f}、股價淨值比 {pb:.2f}，葛拉漢數 {pe * pb:.1f}（≤ 22.5）"})
    return _rank(out, None)


def lynch(ctx):
    out = []
    for code in ctx["codes"]:
        pe = (ctx["value"].get(code) or {}).get("pe")
        g = (ctx["revenue"].get(code) or {}).get("ytd_yoy")
        m60 = ma(ctx, code, 60)
        c = _closes(ctx, code)
        if not pe or pe <= 0 or g is None or not 15 <= g <= 50 or m60 is None or c[-1] < m60:
            continue
        peg = pe / g
        if peg > 1.2:
            continue
        out.append({"code": code, "score": -peg,
                    "reason": f"本益比 {pe:.1f}、今年累計營收 {g:+.1f}%，PEG {peg:.2f}，股價在季線之上"})
    return _rank(out, None)


def _vol(ctx, code):
    s = ctx["px"].get(ctx["sym"][code]) or {}
    return s.get("volume") or []


def oneil(ctx):
    out = []
    for code in ctx["codes"]:
        c, v = _closes(ctx, code), _vol(ctx, code)
        if len(c) < 200 or len(v) < 51:
            continue
        hi = max(c[-252:-1])
        avg = sum(v[-51:-1]) / 50
        if c[-1] < hi or not avg or v[-1] < 1.5 * avg:
            continue
        rs = ret(ctx, code, 126)
        out.append({"code": code, "score": rs if rs is not None else 0,
                    "reason": f"收盤 {c[-1]:g} 創 52 週新高，成交量為 50 日均量 {v[-1] / avg:.1f} 倍，近 6 個月 {rs:+.1f}%"})
    return _rank(out, None)


def _ema(xs, n):
    k, out = 2 / (n + 1), []
    for x in xs:
        out.append(x if not out else out[-1] + k * (x - out[-1]))
    return out


def tech_score(c: list[float]) -> tuple[int, list[str]] | None:
    """kevin801221/stock-strategies-only 的四指標評分（各 25 分）。"""
    if len(c) < 70:
        return None
    score, why = 0, []
    m20, m60 = sum(c[-20:]) / 20, sum(c[-60:]) / 60
    if c[-1] > m20 > m60:
        score += 25; why.append("均線多頭")
    elif c[-1] > m20:
        score += 12; why.append("站上月線")
    sd = (sum((x - m20) ** 2 for x in c[-20:]) / 20) ** 0.5
    lower = m20 - 2 * sd
    if lower > 0 and c[-1] <= lower * 1.03:
        score += 25; why.append("接近布林下緣")
    elif c[-1] < m20:
        score += 10; why.append("布林中線下")
    k = d = 50.0  # KD（9 日）
    for i in range(len(c) - 60, len(c)):
        lo, hi = min(c[i - 8:i + 1]), max(c[i - 8:i + 1])
        rsv = (c[i] - lo) / (hi - lo) * 100 if hi > lo else 50
        k = k * 2 / 3 + rsv / 3
        d = d * 2 / 3 + k / 3
    if k > d and k < 80:
        score += 25; why.append(f"KD 黃金交叉（K {k:.0f}）")
    elif k > d:
        score += 10; why.append("K > D")
    e12, e26 = _ema(c[-120:], 12), _ema(c[-120:], 26)
    dif = [a - b for a, b in zip(e12, e26)]
    dea = _ema(dif, 9)
    hist = dif[-1] - dea[-1]
    if hist > 0 and dif[-1] > dea[-1]:
        score += 25; why.append("MACD 翻正")
    return score, why


def tech4(ctx):
    out = []
    for code in ctx["codes"]:
        r = tech_score(_closes(ctx, code))
        if r and r[0] >= 60:
            out.append({"code": code, "score": r[0], "reason": f"技術分數 {r[0]}：{'、'.join(r[1])}"})
    return _rank(out, None)


def method_weights(ctx) -> dict:
    """每種方法的權重：一開始都是 1，之後依「推薦後 5 天贏大盤多少」和「帳戶近 5 天贏大盤多少」調整。"""
    from .config import METHODS
    perf = ctx.get("perf") or {}
    w = {}
    for m in METHODS:
        if m["id"] in ("claude", "claude2"):
            continue
        p = perf.get(m["id"]) or {}
        x = 1.0
        if (p.get("n") or 0) >= 10 and p.get("avg_excess") is not None:
            x *= min(3.0, max(0.2, 1 + p["avg_excess"] / 2))
        if p.get("recent_excess") is not None:
            x *= min(2.0, max(0.3, 1 + p["recent_excess"] / 5))
        w[m["id"]] = round(x, 2)
    return w


def claude(ctx):
    from .config import METHODS, TOP_N
    names = {m["id"]: m["name"] for m in METHODS}
    w = method_weights(ctx)
    score, fans = {}, {}
    for mid, ranking in (ctx.get("rankings") or {}).items():
        if mid in ("claude", "claude2") or mid not in w:
            continue
        for i, r in enumerate(ranking[:TOP_N]):
            score[r["code"]] = score.get(r["code"], 0) + w[mid] * (TOP_N - i) / TOP_N
            fans.setdefault(r["code"], []).append((w[mid], mid, r["reason"]))
    perf = ctx.get("perf") or {}
    best = sorted(w.items(), key=lambda kv: kv[1], reverse=True)[:3]
    if any(v != 1.0 for v in w.values()):
        ctx["claude_note"] = "目前最準、權重最高的方法：" + "、".join(f"{names[k]}×{v}" for k, v in best)
    else:
        ctx["claude_note"] = "還沒有足夠的成績，各方法先用相同權重"
    out = []
    for code, sc in score.items():
        f = sorted(fans[code], reverse=True)
        lead = f[0]
        hit = (perf.get(lead[1]) or {}).get("hit_rate")
        hit_txt = f"（5 日命中率 {hit:.0f}%）" if hit is not None else ""
        out.append({"code": code, "score": round(sc, 3), "votes": len(f),
                    "reason": f"{len(f)} 種方法看好：{'、'.join(names[x[1]] for x in f)}；共識分數 {sc:.2f}。"
                              f"最有力的理由來自「{names[lead[1]]}」{hit_txt}：{lead[2]}"})
    return _rank(out, None)


def method_weights_long(ctx) -> dict:
    """v2 權重：只看「推薦後 5 天贏大盤多少」的長期平均，樣本少時往 1 收斂（避免被短期運氣帶著走）。"""
    from .config import METHODS
    perf = ctx.get("perf") or {}
    w = {}
    for m in METHODS:
        if m["id"] in ("claude", "claude2", "ai_theme"):
            continue
        p = perf.get(m["id"]) or {}
        n, ex = p.get("n") or 0, p.get("avg_excess")
        shrink = n / (n + 150)
        x = 1 + (ex or 0) * shrink / 1.5
        w[m["id"]] = round(min(2.5, max(0.25, x)), 2)
    return w


def claude2(ctx):
    """v2：加權投票＋不追高（離季線 25% 以內、站上季線）＋本益比 ≤ 25＋同產業最多 1 檔。"""
    from .config import METHODS, TOP_N
    names = {m["id"]: m["name"] for m in METHODS}
    w = method_weights_long(ctx)
    score, fans = {}, {}
    for mid, ranking in (ctx.get("rankings") or {}).items():
        if mid not in w:
            continue
        for i, r in enumerate(ranking[:TOP_N]):
            score[r["code"]] = score.get(r["code"], 0) + w[mid] * (TOP_N - i) / TOP_N
            fans.setdefault(r["code"], []).append((w[mid], mid, r["reason"]))
    best = sorted(w.items(), key=lambda kv: kv[1], reverse=True)[:3]
    ctx["claude2_note"] = ("長期最準、權重最高：" + "、".join(f"{names[k]}×{v}" for k, v in best)
                           if any(v != 1.0 for v in w.values()) else "成績還不夠長，各方法先用相同權重")
    out = []
    for code, sc in score.items():
        c, m60 = _closes(ctx, code), ma(ctx, code, 60)
        if not c or m60 is None or c[-1] < m60 or c[-1] > m60 * 1.25:
            continue
        pe = (ctx["value"].get(code) or {}).get("pe")
        if pe is not None and (pe <= 0 or pe > 25):
            continue
        f = sorted(fans[code], reverse=True)
        lead = f[0]
        pe_txt = f"本益比 {pe:.1f}、" if pe else ""
        out.append({"code": code, "score": round(sc, 3), "votes": len(f),
                    "reason": f"{len(f)} 種方法看好（{'、'.join(names[x[1]] for x in f)}），共識分數 {sc:.2f}；"
                              f"{pe_txt}股價在季線上方 {(c[-1] / m60 - 1) * 100:.0f}%（沒有過熱）。主要理由：{lead[2]}"})
    out = _rank(out, None)
    seen, picked, rest = set(), [], []
    for r in out:  # 同一條產業鏈最多 1 檔，分散風險
        ch = (ctx["chain_of"].get(r["code"]) or [r["code"]])[0]
        (rest if ch in seen else picked).append(r)
        seen.add(ch)
    return picked + rest


METHOD_FNS = {"momentum": momentum, "reversal": reversal, "revenue": revenue, "trust": trust,
              "foreign": foreign, "value": value, "chain": chain, "ai_theme": ai_theme, "combo": combo,
              "graham": graham, "lynch": lynch, "oneil": oneil, "tech4": tech4, "claude": claude, "claude2": claude2}
