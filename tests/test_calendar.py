from datetime import date
from functools import partial

from briefing import config
from briefing.__main__ import build
from briefing.calendar import build_calendar, macro_name, parse_dividends
from briefing.market import build_market
from briefing.news import fetch_news

from tests.fakes import FAKE_TWT48U, fake_history, fake_parse, fake_twse


def test_macro_names():
    assert macro_name("Core CPI m/m", "USD") == "美國 CPI"
    assert macro_name("Non-Farm Employment Change", "USD") == "美國非農就業"
    assert macro_name("German Prelim CPI m/m", "EUR") == "歐元區 German Prelim CPI m/m"
    assert macro_name("BOJ Policy Rate", "JPY") == "日銀利率決策"


def test_dividends_window_and_watch():
    ev, others = parse_dividends(FAKE_TWT48U, date(2026, 11, 8), date(2026, 11, 15), config.CALENDAR_DIV_WATCH)
    assert [e["title"] for e in ev] == ["元大高股息（0056）除息"]
    assert ev[0]["note"] == "現金股利 0.866 元" and ev[0]["date"] == "2026-11-13"
    assert others == 1


def test_build_calendar_merges_and_sorts():
    earn = lambda syms: {"NVDA": date(2026, 11, 12), "2330.TW": date(2026, 11, 9)}  # noqa: E731
    c = build_calendar(config, today=date(2026, 11, 8), get_json=fake_twse, earnings_fn=earn)
    titles = [(e["date"], e["time"], e["title"]) for e in c["events"]]
    # CPI 月增、核心合併成一筆，台灣時間 21:30；Medium 與澳洲不列
    assert ("2026-11-10", "21:30", "美國 CPI") in titles
    assert sum(1 for t in titles if t[2] == "美國 CPI") == 1
    assert not any("Retail" in t[2] or "RBA" in t[2] or "German" in t[2] for t in titles)
    assert ("2026-11-09", "", "台積電 法說會／財報") in titles
    assert ("2026-11-12", "", "NVIDIA 財報") in titles
    assert titles == sorted(titles, key=lambda t: (t[0], t[1] or "99:99", t[2]))
    assert c["sources"] == ["總經", "財報", "除權息"]


def test_fomc_shows_in_taiwan_time():
    c = build_calendar(config, today=date(2026, 12, 7), get_json=lambda u: [], earnings_fn=lambda s: {})
    fed = [e for e in c["events"] if e["title"] == "Fed 利率決策"]
    assert fed == [{"date": "2026-12-10", "time": "03:00", "kind": "fed", "title": "Fed 利率決策",
                    "note": "美東 14:00 公布，台灣時間隔天凌晨"}]


def test_build_keeps_previous_calendar_when_all_down(tmp_path):
    kw = dict(market_fn=partial(build_market, history_fn=fake_history),
              news_fn=partial(fetch_news, parse=fake_parse), summary_fn=lambda m, n: None)
    good = build(tmp_path, calendar_fn=lambda cfg: {"events": [{"title": "x"}], "sources": ["總經"]}, **kw)
    bad = build(tmp_path, calendar_fn=lambda cfg: {"events": [], "sources": []}, **kw)
    assert bad["calendar"] == good["calendar"]
