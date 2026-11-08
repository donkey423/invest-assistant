"""把早報與警報排成 LINE 文字。數字只照抄 JSON，不另外計算。"""
from __future__ import annotations

import os


def _arrow(v) -> str:
    if v is None:
        return "—"
    return f"{'▲' if v > 0 else '▼' if v < 0 else '＝'}{abs(v):.2f}%"


def brief_text(brief: dict) -> str:
    s, m = brief.get("summary") or {}, brief.get("market") or {}
    lines = [f"📰 投資早報 {brief.get('generated_at', '')[:16].replace('T', ' ')}"]
    if s.get("headline"):
        lines += ["", s["headline"]]
    t = m.get("taiex") or {}
    if t and "error" not in t:
        lines += ["", f"{t['name']} {t['last']:,} {_arrow(t.get('change_pct'))}"]
    glob = [q for q in m.get("global", []) if "error" not in q]
    if glob:
        lines += ["", "【全球股市】"] + [f"{q['name']} {_arrow(q.get('change_pct'))}" for q in glob]
    ai = [q for q in m.get("ai_stocks", []) if "error" not in q]
    if ai:
        lines += ["", "【美國 AI 股】"] + [f"{q['name']} {q['last']:,} {_arrow(q.get('change_pct'))}" for q in ai]
    pts = s.get("points") or []
    if pts:
        lines += ["", "【財經重點】"]
        for i, p in enumerate(pts, 1):
            lines.append(f"{i}. [{p.get('tag', '')}] {p.get('title', '')}")
            if p.get("summary"):
                lines.append(f"   {p['summary']}")
    themes = s.get("themes") or []
    if themes:
        lines += ["", "【主題推理】"]
        for t in themes:
            lines.append(f"・{t.get('title', '')}（{t.get('chain', '')}）")
            lines.append(f"   觀察：{'、'.join(t.get('watch') or [])}")
            if t.get("counter"):
                lines.append(f"   反方：{t['counter']}")
    for w in brief.get("warnings") or []:
        lines += ["", f"⚠ {w}"]
    site = os.environ.get("SITE_URL")
    if site:
        lines += ["", f"完整早報：{site}"]
    lines += ["", "AI 整理，僅供參考，不構成投資建議。"]
    return "\n".join(lines)


def alerts_text(alerts: list[dict]) -> str:
    lines = [f"🔔 投資警報（{len(alerts)} 則）"]
    for a in alerts:
        lines += ["", a["text"]]
        if a.get("url"):
            lines.append(a["url"])
    return "\n".join(lines)
