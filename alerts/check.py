"""價格與事件警報的判斷。純函式，不連網，方便測試。

去重規則：
- 價格條件：同一檔、同一種條件，一個台灣日期只通知一次。
- 事件：同一則新聞（依連結或標題）只通知一次。
"""
from __future__ import annotations

import re

STATE_KEEP_EVENTS = 500


def _price_alerts(rule: dict, q: dict) -> list[tuple[str, str]]:
    """回傳 [(條件代碼, 說明文字)]。"""
    name, last, pct = rule.get("name") or q.get("name") or rule["symbol"], q["last"], q.get("change_pct")
    out = []
    if rule.get("above") is not None and last >= rule["above"]:
        out.append(("above", f"📈 {name} 漲破 {rule['above']:,}，現在 {last:,}"))
    if rule.get("below") is not None and last <= rule["below"]:
        out.append(("below", f"📉 {name} 跌破 {rule['below']:,}，現在 {last:,}"))
    if rule.get("move_pct") is not None and pct is not None and abs(pct) >= rule["move_pct"]:
        word = "大漲" if pct > 0 else "大跌"
        out.append((f"move_{'up' if pct > 0 else 'down'}",
                    f"{'🚀' if pct > 0 else '⚠️'} {name} 今日{word} {pct:+.2f}%（門檻 {rule['move_pct']}%），現在 {last:,}"))
    if rule.get("new_52w"):
        if q.get("high_52w") is not None and last >= q["high_52w"]:
            out.append(("high_52w", f"🏔 {name} 創一年新高 {last:,}"))
        elif q.get("low_52w") is not None and last <= q["low_52w"]:
            out.append(("low_52w", f"🕳 {name} 創一年新低 {last:,}"))
    return out


def _news_key(n: dict) -> str:
    return n.get("url") or re.sub(r"\W", "", n.get("title", ""))[:40]


def evaluate(rules: dict, quotes: dict[str, dict], news: list[dict], state: dict, today: str):
    """quotes: {symbol: compute_quote 的結果}；today: 台灣日期 YYYY-MM-DD。

    回傳 (alerts, new_state)。alerts 每筆 {kind, key, text, url?}。
    """
    fired = dict(state.get("fired", {}))
    # 只留今天的價格紀錄
    fired = {k: v for k, v in fired.items() if v == today}
    seen = list(state.get("seen_news", []))
    seen_set = set(seen)
    alerts = []

    for rule in rules.get("price", []):
        q = quotes.get(rule["symbol"])
        if not q or "error" in q:
            continue
        for code, text in _price_alerts(rule, q):
            key = f"{rule['symbol']}:{code}"
            if key in fired:
                continue
            fired[key] = today
            alerts.append({"kind": "price", "key": key, "text": text})

    for ev in rules.get("events", []):
        kws = [k.lower() for k in ev.get("keywords", [])]
        for n in news:
            title = n.get("title", "")
            hay = title.lower()
            # 關鍵字裡的空白代表「兩個詞都要出現」
            hit = next((k for k in kws if all(part in hay for part in k.split())), None)
            if not hit:
                continue
            nk = _news_key(n)
            if nk in seen_set:
                continue
            seen_set.add(nk)
            seen.append(nk)
            alerts.append({"kind": "event", "key": nk, "url": n.get("url"),
                           "text": f"🗞 [{ev['name']}] {title}（{n.get('source', '')}）"})

    return alerts, {"fired": fired, "seen_news": seen[-STATE_KEEP_EVENTS:]}


def prime_news(news: list[dict], state: dict) -> dict:
    """第一次執行時把現有新聞標成已讀，避免一次轟炸。"""
    seen = list(state.get("seen_news", [])) + [_news_key(n) for n in news]
    return {**state, "seen_news": seen[-STATE_KEEP_EVENTS:], "primed": True}
