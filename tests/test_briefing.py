import json
from functools import partial

import pytest

from briefing import config
from briefing.__main__ import build
from briefing.market import build_market, compute_quote
from briefing.news import fetch_news
from briefing.notify import render_email
from briefing.summarize import SCHEMA, summarize

from tests.fakes import FakeClient, fake_history, fake_parse


def test_compute_quote_basic():
    dates = [f"d{i}" for i in range(300)]
    closes = [100 + i for i in range(300)]
    q = compute_quote(dates, closes, spark_days=60)
    assert q["last"] == 399
    assert q["change_pct"] == round((399 / 398 - 1) * 100, 2)
    assert q["chg_5d"] == round((399 / 394 - 1) * 100, 2)
    assert q["high_52w"] == 399 and q["low_52w"] == 148
    assert q["range_pos"] == 1.0
    assert len(q["spark"]) == 60 and q["as_of"] == "d299"


def test_compute_quote_short_history_does_not_crash():
    q = compute_quote(["a", "b", "c"], [10, 11, 9], spark_days=60)
    assert q["chg_1y"] == -10.0 and q["range_pos"] == 0.0


def test_market_skips_missing_symbol():
    def hist(symbols):
        h = fake_history(list(symbols))
        h.pop("^NSEI")
        return h
    m = build_market(config, history_fn=hist)
    assert "error" in next(q for q in m["global"] if q["symbol"] == "^NSEI")
    assert len(m["taiex"]["spark"]) == config.TAIEX_CHART_DAYS
    assert len(m["taiex"]["spark_dates"]) == config.TAIEX_CHART_DAYS


def test_news_dedup_and_failing_feed():
    def parse(url):
        if "cnyes" in url:
            raise OSError("down")
        return fake_parse(url)
    news = fetch_news(config, parse=parse)
    titles = [n["title"] for n in news]
    assert len(titles) == len(set(titles))
    assert not any(n["source"] == "鉅亨網 台股" for n in news)


def test_summarize_maps_sources_and_sets_fallback():
    market = build_market(config, history_fn=fake_history)
    news = fetch_news(config, parse=fake_parse)
    client = FakeClient()
    s = summarize(market, news, client=client)
    call = client.calls[0]
    assert call["fallbacks"] == "default"
    assert call["output_config"]["format"]["schema"] is SCHEMA
    assert all("news_ids" not in p for p in s["points"])
    assert s["points"][0]["sources"][0]["url"].startswith("https://")


def test_summarize_refusal_raises():
    market = build_market(config, history_fn=fake_history)
    with pytest.raises(RuntimeError):
        summarize(market, [{"title": "t", "summary": "", "url": "u", "source": "s"}],
                  client=FakeClient(stop_reason="refusal"))


def test_build_keeps_previous_summary_when_ai_fails(tmp_path):
    ok = build(tmp_path, market_fn=partial(build_market, history_fn=fake_history),
               news_fn=partial(fetch_news, parse=fake_parse),
               summary_fn=lambda m, n: summarize(m, n, client=FakeClient()))
    assert ok["summary"]["headline"] and not ok["warnings"]

    def boom(m, n):
        raise RuntimeError("api down")
    again = build(tmp_path, market_fn=partial(build_market, history_fn=fake_history),
                  news_fn=partial(fetch_news, parse=fake_parse), summary_fn=boom)
    assert again["summary"] == ok["summary"]
    assert again["warnings"]
    saved = json.loads((tmp_path / "latest.json").read_text("utf-8"))
    assert saved["warnings"] == again["warnings"]
    assert len(list((tmp_path / "archive").iterdir())) >= 1


def test_build_refuses_when_no_market_data(tmp_path):
    with pytest.raises(RuntimeError):
        build(tmp_path, market_fn=partial(build_market, history_fn=lambda s: {}),
              news_fn=lambda c: [], summary_fn=lambda m, n: None)


def test_email_renders():
    market = build_market(config, history_fn=fake_history)
    subject, body = render_email({"generated_at": "2026-11-07T07:30+08:00", "market": market,
                                  "summary": {"headline": "<測試>", "market_comment": "", "points": []}})
    assert "&lt;測試&gt;" in body and subject.startswith("投資早報 2026-11-07")


def test_free_mode_without_api_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    market = build_market(config, history_fn=fake_history)
    news = fetch_news(config, parse=fake_parse)
    s = summarize(market, news)
    assert s["model"].startswith("免費模式")
    assert "台股加權指數" in s["headline"]
    assert 0 < len(s["points"]) <= 6
    assert all(p["sources"][0]["url"] == next(n["url"] for n in news if n["title"] == p["title"]) for p in s["points"])
    assert len({p["sources"][0]["source"] for p in s["points"]}) > 1


def test_merge_series_fills_holes_and_newer_days():
    from briefing.market import merge_series
    base = (["2026-11-05", "2026-11-06", "2026-11-10"], [1.0, 2.0, 4.0])     # 少了 11/9
    extra = (["2026-11-04", "2026-11-06", "2026-11-09", "2026-11-11"], [0.5, 2.5, 3.0, 5.0])
    days = ["2026-11-05", "2026-11-06", "2026-11-09", "2026-11-10", "2026-11-11"]
    assert merge_series(base, extra) == (days, [1.0, 2.5, 3.0, 4.0, 5.0])
    assert merge_series(base, extra, fill_only=True) == (days, [1.0, 2.0, 3.0, 4.0, 5.0])
    assert merge_series(base, None) == base and merge_series(None, extra) == extra


def test_taiex_uses_twse_close_when_yahoo_lags():
    from briefing.market import parse_fmtqik
    official = parse_fmtqik({"stat": "OK", "fields": ["日期", "成交股數", "成交金額", "成交筆數", "發行量加權股價指數", "漲跌點數"],
                             "data": [["115/11/06", "1", "1", "1", "39,701.64", "-1873.08"],
                                      ["115/11/09", "1", "1", "1", "41,661.70", "1960.06"]]})
    assert official == (["2026-11-06", "2026-11-09"], [39701.64, 41661.7])

    def hist(symbols):
        return {s: (["2026-11-05", "2026-11-06"], [41574.72, 39701.64]) for s in symbols}

    m = build_market(config, history_fn=hist, taiex_fn=lambda: official, today="2026-11-10")
    assert m["taiex"]["as_of"] == "2026-11-09" and m["taiex"]["last"] == 41661.7
    assert m["taiex"]["change_pct"] == 4.94 and "stale" not in m["taiex"]
    assert m["global"][0]["stale"] is True          # 週二早上還停在上週五

    # Yahoo 有今天盤中價、卻少了昨天：漲跌幅要對昨天算，不是對上週五
    def hole(symbols):
        return {s: (["2026-11-05", "2026-11-06", "2026-11-10"], [41574.72, 39701.64, 42841.4]) for s in symbols}

    m = build_market(config, history_fn=hole, taiex_fn=lambda: official, today="2026-11-10")
    assert m["taiex"]["as_of"] == "2026-11-10" and m["taiex"]["change_pct"] == 2.83


def test_keep_newer_never_goes_back_in_time():
    from briefing.market import keep_newer
    prev = {"taiex": {"symbol": "^TWII", "as_of": "2026-11-09", "last": 41661.7},
            "global": [{"symbol": "^N225", "as_of": "2026-11-09", "last": 2.0}], "ai_stocks": [], "gauges": []}
    new = {"taiex": {"symbol": "^TWII", "as_of": "2026-11-06", "last": 39701.64},
           "global": [{"symbol": "^N225", "error": "抓不到資料"}],
           "ai_stocks": [{"symbol": "NVDA", "as_of": "2026-11-09", "last": 1.0}], "gauges": []}
    out = keep_newer(new, prev, today="2026-11-10")
    assert out["taiex"]["last"] == 41661.7 and out["taiex"]["kept_previous"]
    assert out["global"][0]["last"] == 2.0 and out["ai_stocks"][0]["last"] == 1.0


def test_prune_archive_keeps_recent_runs_and_one_per_older_day(tmp_path):
    from datetime import date
    from briefing.__main__ import prune_archive
    names = ["2026-07-01_0730.json", "2026-11-01_0730.json", "2026-11-01_1400.json",
             "2026-11-09_0730.json", "2026-11-09_1400.json", "notes.json"]
    for n in names:
        (tmp_path / n).write_text("{}")
    removed = prune_archive(tmp_path, date(2026, 11, 10))
    assert sorted(removed) == ["2026-07-01_0730.json", "2026-11-01_0730.json"]
    assert (tmp_path / "notes.json").exists() and (tmp_path / "2026-11-09_0730.json").exists()
