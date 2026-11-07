"""「今天的世界」：從新聞標題統計各地區的熱度，挑出 AI 世界動態。

全部由程式統計，不需要 AI。若雲端排程用你的 Claude 帳號寫了
world_headline / ai_headline，會取代這裡算出來的一句話。
"""
from __future__ import annotations

from collections import Counter

PER_REGION = 5
AI_MAX = 10


def _text(n: dict) -> str:
    return f"{n['title']} {n.get('summary', '')}"


def _brief(n: dict) -> dict:
    return {k: n.get(k) for k in ("title", "url", "source", "published")}


def _has(text: str, words) -> list[str]:
    return [w for w in words if w in text]


def regions(cfg, news: list[dict]) -> list[dict]:
    out = []
    for r in cfg.REGIONS:
        hits = [n for n in news if _has(_text(n), r["words"])]
        risk = Counter(w for n in hits for w in _has(n["title"], cfg.RISK_WORDS))
        out.append({
            "id": r["id"], "name": r["name"], "lon": r["lon"], "lat": r["lat"],
            "label_lon": r.get("label_lon", r["lon"]), "label_lat": r.get("label_lat", r["lat"]),
            "count": len(hits),
            "risk": [w for w, _ in risk.most_common(3)],
            "news": [_brief(n) for n in hits[:PER_REGION]],
        })
    return out


def ai_news(cfg, news: list[dict]) -> list[dict]:
    out = []
    for n in news:
        if not _has(n["title"], cfg.AI_WORDS):
            continue
        cat = next((name for name, words in cfg.AI_CATEGORIES if _has(n["title"], words)), "應用")
        out.append({**_brief(n), "category": cat})
        if len(out) >= AI_MAX:
            break
    return out


def world_headline(regs: list[dict]) -> str:
    top = [r for r in sorted(regs, key=lambda r: -r["count"]) if r["count"]][:3]
    if not top:
        return "今天沒有抓到國際新聞"
    s = "今天新聞最多的地區：" + "、".join(f"{r['name']} {r['count']} 則" for r in top)
    risky = [r["name"] for r in regs if r["risk"]]
    if risky:
        s += f"；{('、'.join(risky[:3]))}出現衝突或關稅等字眼，值得留意"
    return s + "。"


def ai_headline(items: list[dict]) -> str:
    if not items:
        return "今天沒有抓到 AI 相關新聞"
    cats = Counter(i["category"] for i in items).most_common()
    mix = "、".join(f"{c} {k} 則" for c, k in cats)
    return f"AI 新聞 {len(items)} 則（{mix}），最新：{items[0]['title']}"


def build_world(cfg, news: list[dict], summary: dict | None = None) -> dict:
    regs = regions(cfg, news)
    ai = ai_news(cfg, news)
    summary = summary or {}
    return {
        "headline": summary.get("world_headline") or world_headline(regs),
        "ai_headline": summary.get("ai_headline") or ai_headline(ai),
        "by_ai": bool(summary.get("world_headline")),
        "news_count": len(news),
        "regions": regs,
        "ai_news": ai,
    }
