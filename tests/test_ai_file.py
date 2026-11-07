import json
from datetime import datetime, timedelta
from functools import partial

from briefing import config
from briefing.__main__ import build
from briefing.ai_file import FILE_NAME, TW, load_fresh, main, validate
from briefing.market import build_market
from briefing.news import fetch_news
from briefing.summarize import FREE_MODEL, simple_summary

from tests.fakes import fake_history, fake_parse

NOW = datetime(2026, 11, 9, 8, 0, tzinfo=TW)


def _ai(written_at="2026-11-09T07:50+08:00", n=3, tag="央行"):
    return {
        "written_at": written_at,
        "headline": "就業降溫，台股反彈",
        "market_comment": "說明。",
        "points": [{"tag": tag, "title": f"重點{i}", "summary": "意義",
                    "sources": [{"title": "t", "url": f"https://example.com/{i}", "source": "s"}]}
                   for i in range(n)],
    }


def test_validate_ok_and_problems():
    assert validate(_ai()) == []
    assert any("3 到 6" in p for p in validate(_ai(n=2)))
    assert any("tag" in p for p in validate(_ai(tag="其他")))
    assert any("不在 news.json" in p for p in validate(_ai(), news_urls={"https://other"}))


def test_load_fresh_respects_age(tmp_path):
    (tmp_path / FILE_NAME).write_text(json.dumps(_ai(), ensure_ascii=False), "utf-8")
    s = load_fresh(tmp_path, now=NOW)
    assert s["headline"] and "你的帳號" in s["model"]
    assert load_fresh(tmp_path, now=NOW + timedelta(hours=11)) is None
    assert load_fresh(tmp_path, now=NOW - timedelta(hours=1)) is None  # 未來時間不算


def test_load_fresh_ignores_bad_file(tmp_path):
    (tmp_path / FILE_NAME).write_text("{not json", "utf-8")
    assert load_fresh(tmp_path, now=NOW) is None


def test_build_uses_account_summary_in_free_mode(tmp_path, monkeypatch):
    now = datetime.now(TW)
    (tmp_path / FILE_NAME).write_text(
        json.dumps(_ai(written_at=(now - timedelta(minutes=5)).isoformat(timespec="minutes"))), "utf-8")
    b = build(tmp_path, market_fn=partial(build_market, history_fn=fake_history),
              news_fn=partial(fetch_news, parse=fake_parse), summary_fn=simple_summary)
    assert "你的帳號" in b["summary"]["model"]
    news = json.loads((tmp_path / "news.json").read_text("utf-8"))
    assert news and "url" in news[0]


def test_build_stays_free_without_file(tmp_path):
    b = build(tmp_path, market_fn=partial(build_market, history_fn=fake_history),
              news_fn=partial(fetch_news, parse=fake_parse), summary_fn=simple_summary)
    assert b["summary"]["model"] == FREE_MODEL


def test_check_cli(tmp_path, capsys):
    (tmp_path / FILE_NAME).write_text(json.dumps(_ai(), ensure_ascii=False), "utf-8")
    assert main(["x", "check", str(tmp_path)]) == 0
    (tmp_path / FILE_NAME).write_text(json.dumps(_ai(n=1), ensure_ascii=False), "utf-8")
    assert main(["x", "check", str(tmp_path)]) == 1
