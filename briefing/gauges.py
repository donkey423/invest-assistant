"""市場溫度計：VIX、美債、美元、台幣、費半、黃金、原油、比特幣的白話解讀。

數字由 market.compute_quote 算好，這裡只依規則寫一句話，不用 AI。
"""
from __future__ import annotations


def _pct(v: float | None) -> str:
    return "—" if v is None else f"{v:+.2f}%"


def _vix(q: dict) -> str:
    v = q["last"]
    if v < 15:
        mood = "市場很平靜"
    elif v < 20:
        mood = "市場情緒平穩"
    elif v < 30:
        mood = "市場有點緊張"
    else:
        mood = "市場恐慌，波動會很大"
    return f"{mood}（20 以下算平穩、30 以上算恐慌）"


def _yield(q: dict) -> str:
    # ^TNX 的報價就是殖利率（%），變動換算成基點（0.01% = 1 個基點）
    day = round(q["change"] * 100)
    closes = q.get("spark") or []
    month = round((closes[-1] - closes[-22]) * 100) if len(closes) >= 22 else None
    text = f"今天 {day:+d} 個基點"
    if month is None:
        return text
    text += f"，近一個月 {month:+d} 個基點"
    if month >= 15:
        return text + "，利率走高對科技股是壓力"
    if month <= -15:
        return text + "，利率走低對成長股有利"
    return text + "，變化不大"


def _dxy(q: dict) -> str:
    m = q.get("chg_1m") or 0
    if m >= 1:
        return f"近一個月 {_pct(m)}，美元走強，資金偏向美國"
    if m <= -1:
        return f"近一個月 {_pct(m)}，美元走弱，有利資金流向亞洲"
    return f"近一個月 {_pct(m)}，美元大致持平"


def _twd(q: dict) -> str:
    # 美元兌台幣上升 = 台幣貶值
    d = q.get("change_pct") or 0
    m = q.get("chg_1m") or 0
    today = "台幣今天貶值" if d > 0 else "台幣今天升值" if d < 0 else "台幣今天持平"
    if m >= 1:
        return f"{today}；近一個月貶 {abs(m):.1f}%，留意外資匯出"
    if m <= -1:
        return f"{today}；近一個月升 {abs(m):.1f}%，外資資金偏流入"
    return f"{today}；近一個月變化不大"


def _sox(q: dict) -> str:
    d = q.get("change_pct") or 0
    if abs(d) >= 2:
        return f"今天{'大漲' if d > 0 else '大跌'} {abs(d):.1f}%，台積電與電子股容易跟著反應"
    return "跟台股電子股連動最高的美國指數"


def _generic(what: str):
    def note(q: dict) -> str:
        return f"近一個月 {_pct(q.get('chg_1m'))}，{what}"
    return note


NOTES = {
    "vix": _vix,
    "yield": _yield,
    "dxy": _dxy,
    "twd": _twd,
    "sox": _sox,
    "gold": _generic("避險需求的溫度計"),
    "oil": _generic("影響通膨與塑化、航運股"),
    "btc": _generic("市場風險胃納的指標"),
}


def gauge_note(q: dict) -> str:
    if "error" in q:
        return ""
    try:
        return NOTES.get(q.get("kind"), _generic(""))(q)
    except Exception:  # noqa: BLE001 解讀失敗就不顯示，不影響數字
        return ""
