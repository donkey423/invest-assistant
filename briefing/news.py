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
            "topic": feed.get("topic", "finance"),
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
            # Google 新聞標題結尾是「 - 媒體名」，同一則新聞不同媒體只留一則
            key = re.sub(r"\W", "", re.sub(r"\s+-\s+[^-]+$", "", it["title"]))[:40]
            if key in seen:
                continue
            seen.add(key)
            out.append(it)
    return _cap(out, cfg.NEWS_MAX_TOTAL)


def _cap(items: list[dict], total: int) -> list[dict]:
    """新的排前面，總數不超過 total；財經、國際、AI 各保留一份，不會被其中一類擠光。"""
    newest = lambda i: i["published"] or ""  # noqa: E731
    items = sorted(items, key=newest, reverse=True)
    topics = sorted({i["topic"] for i in items})
    share = total // max(1, len(topics))
    keep, rest = [], []
    for t in topics:
        group = [i for i in items if i["topic"] == t]
        keep += group[:share]
        rest += group[share:]
    keep += sorted(rest, key=newest, reverse=True)[: total - len(keep)]
    return sorted(keep, key=newest, reverse=True)
