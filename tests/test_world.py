
from briefing import config
from briefing.news import _cap, fetch_news
from briefing.world import build_world

from tests.fakes import fake_parse


def _news():
    return fetch_news(config, parse=fake_parse)


def test_regions_count_and_risk():
    w = build_world(config, _news())
    by = {r["id"]: r for r in w["regions"]}
    assert by["me"]["count"] >= 2  # 以色列伊朗、油價
    assert "衝突" in by["me"]["risk"]
    assert by["ru"]["count"] == 1 and "停火" in by["ru"]["risk"]
    assert by["tw"]["count"] >= 2 and by["tw"]["news"][0]["url"].startswith("https://")
    assert "中東" in w["headline"] and not w["by_ai"]


def test_ai_news_categories():
    w = build_world(config, _news())
    cats = {n["title"]: n["category"] for n in w["ai_news"]}
    assert cats["OpenAI 發表新模型，企業版價格下調"] == "模型"
    assert cats["輝達黃仁勳：AI 資料中心需求明年翻倍"] == "晶片"
    assert "AI 新聞" in w["ai_headline"]


def test_account_headlines_win():
    w = build_world(config, _news(), {"world_headline": "帳號寫的", "ai_headline": "AI 帳號寫的"})
    assert w["headline"] == "帳號寫的" and w["ai_headline"] == "AI 帳號寫的" and w["by_ai"]


def test_cap_keeps_every_topic():
    items = [{"title": f"f{i}", "topic": "finance", "published": f"2026-11-07T{i:02d}"} for i in range(20)]
    items += [{"title": "w", "topic": "world", "published": "2026-01-01"}]
    out = _cap(items, 10)
    assert len(out) == 10 and any(i["topic"] == "world" for i in out)
