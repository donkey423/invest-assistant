"""從 RSS 抓財經新聞標題與摘要。只存標題、短摘要與連結，不轉載全文。"""
from __future__ import annotations

import html
import logging
import re
from datetime import datetime, timezone

log = logging.getLogger(__name__)
_TAG = re.compile(r"<[^>]+>")


def _clean(text: str, limit: int = 160) -> str:
    text = html.unescape(_TAG.sub(" ", text or ""))
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit]


def _published(entry) -> str | None:
    t = entry.get("published_parsed") or entry.get("updated_parsed")
    if not t:
        return None
    return datetime(*t[:6], tzinfo=timezone.utc).isoformat()


def parse_feed(feed: dict, parsed, per_feed: int) -> list[dict]:
    items = []
    for e in parsed.entries[:per_feed]:
        title = _clean(e.get("title", ""), 200)
        if not title:
            continue
        summary = _clean(e.get("summary", ""))
        items.append({
            "title": title,
            # Google 新聞的摘要常常只是重複標題，就不送
            "summary": "" if summary.startswith(title[:20]) else summary,
            "url": e.get("link", ""),
            "source": feed["name"],
            "published": _published(e),
        })
    return items


def fetch_news(cfg, parse=None) -> list[dict]:
    """抓所有來源、依標題去重、新的排前面。parse 可替換成測試用的假資料。"""
    if parse is None:
        import feedparser
        parse = feedparser.parse

    seen, out = set(), []
    for feed in cfg.NEWS_FEEDS:
        try:
            items = parse_feed(feed, parse(feed["url"]), cfg.NEWS_PER_FEED)
        except Exception as e:  # noqa: BLE001 單一來源失敗不影響其他
            log.warning("抓不到 %s：%s", feed["name"], e)
            continue
        for it in items:
            key = re.sub(r"\W", "", it["title"])[:40]
            if key in seen:
                continue
            seen.add(key)
            out.append(it)
    out.sort(key=lambda i: i["published"] or "", reverse=True)
    return out[: cfg.NEWS_MAX_TOTAL]
