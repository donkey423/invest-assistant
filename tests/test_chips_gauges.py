from datetime import date
from functools import partial

from briefing import chips, config
from briefing.__main__ import build
from briefing.gauges import gauge_note
from briefing.market import build_market
from briefing.news import fetch_news

from tests.fakes import FAKE_BFI82U, FAKE_MI_MARGN, fake_history, fake_parse, fake_twse


def test_parse_institutional():
    r = chips.parse_institutional(FAKE_BFI82U)
    assert r == {"date": "2026-11-06", "foreign": 52.0, "trust": 8.0, "dealer": -2.0, "total": 58.0}
    assert chips.parse_institutional({"stat": "很抱歉，沒有符合條件的資料!"}) is None


def test_parse_margin_new_and_old_format():
    r = chips.parse_margin(FAKE_MI_MARGN)
    assert r["margin_balance"] == 3467.0 and r["margin_change"] == 17.0
    assert r["short_lots"] == 251000 and r["short_change"] == 1000
    assert r["short_ratio"] == round(251000 / 8015000 * 100, 2)
    old = {"stat": "OK", "date": "20261106", "creditList": FAKE_MI_MARGN["tables"][0]["data"]}
    assert chips.parse_margin(old)["margin_balance"] == 3467.0


def test_streak():
    h = [{"foreign": -1}, {"foreign": 2}, {"foreign": 3}, {"foreign": 1}]
    assert chips.streak(h, "foreign") == 3
    assert chips.streak(h[:1], "foreign") == -1
    assert chips.streak([], "foreign") == 0


def test_build_chips_skips_weekend_and_keeps_history(monkeypatch):
    seen = []

    def fake(url):
        seen.append(url)
        if "20261106" not in url:  # 只有週五有資料
            return {"stat": "沒有資料"}
        return fake_twse(url)
    monkeypatch.setattr(chips, "_get_json", fake)
    prev = {"history": [{"date": "2026-11-04", "foreign": 10, "trust": 0, "dealer": 0},
                        {"date": "2026-11-05", "foreign": 20, "trust": 0, "dealer": 0}]}
    c = chips.build_chips(config, prev, today=date(2026, 11, 8))  # 週日
    assert not any("20261108" in u or "20261107" in u for u in seen)
    assert [h["date"] for h in c["history"]] == ["2026-11-04", "2026-11-05", "2026-11-06"]
    assert c["foreign_streak"] == 3
    assert "連 3 天買超" in c["notes"][0] and "融資餘額 3,467 億" in c["notes"][1]
    # 同一天再跑一次不會重複記
    again = chips.build_chips(config, c, today=date(2026, 11, 8))
    assert len(again["history"]) == 3


def test_build_chips_returns_none_when_offline():
    assert chips.build_chips(config, {}, today=date(2026, 11, 6)) is None


def test_gauges_in_market_with_notes():
    m = build_market(config, history_fn=fake_history)
    assert [g["symbol"] for g in m["gauges"]] == [g["symbol"] for g in config.GAUGES]
    assert all(g["note"] for g in m["gauges"])


def test_gauge_notes_rules():
    assert "恐慌" in gauge_note({"kind": "vix", "last": 35})
    assert "平穩" in gauge_note({"kind": "vix", "last": 17})
    q = {"kind": "yield", "change": 0.05, "spark": [4.0] * 21 + [4.3]}
    assert gauge_note(q).startswith("今天 +5 個基點，近一個月 +30 個基點") and "壓力" in gauge_note(q)
    assert "貶值" in gauge_note({"kind": "twd", "change_pct": 0.3, "chg_1m": 1.5})
    assert gauge_note({"kind": "vix", "error": "x"}) == ""


def test_build_keeps_previous_chips_when_twse_down(tmp_path, monkeypatch):
    kw = dict(market_fn=partial(build_market, history_fn=fake_history),
              news_fn=partial(fetch_news, parse=fake_parse), summary_fn=lambda m, n: None)
    monkeypatch.setattr(chips, "_get_json", fake_twse)
    first = build(tmp_path, **kw)
    assert first["market"]["chips"]["institutional"]["foreign"] == 52.0
    monkeypatch.setattr(chips, "_get_json", lambda u: (_ for _ in ()).throw(OSError("down")))
    second = build(tmp_path, **kw)
    assert second["market"]["chips"] == first["market"]["chips"]
