import json

from alerts.__main__ import run_check
from alerts.check import evaluate
from briefing import config
from briefing.__main__ import build
from briefing.ai_file import validate
from briefing.signals import build_signals, merge_history, parse_revenue, revenue_events

from tests.fakes import fake_history, fake_parse
from tests.test_ai_file import _ai

# openapi 月營收彙總表的格式（數字是編的）
ROW = {"出表日期": "1151107", "資料年月": "11510", "公司代號": "2408", "公司名稱": "南亞科", "產業別": "半導體業",
       "營業收入-當月營收": "12,000,000", "營業收入-上月營收": "10000000", "營業收入-去年當月營收": "6000000",
       "營業收入-上月比較增減(%)": "20.00", "營業收入-去年同月增減(%)": "100.00",
       "累計營業收入-當月累計營收": "90000000", "累計營業收入-去年累計營收": "60000000",
       "累計營業收入-前期比較增減(%)": "50.00", "備註": "-"}


def test_parse_revenue_roc_month_and_numbers():
    r = parse_revenue([ROW, {"公司代號": "x"}])["2408"]
    assert r == {"ym": "2026-10", "name": "南亞科", "rev": 12000000.0, "yoy": 100.0, "mom": 20.0, "ytd_yoy": 50.0}


def test_revenue_events_turn_accel_and_new_high():
    hist = [{"ym": f"2025-{m:02d}", "rev": 5e6, "yoy": -5.0} for m in range(1, 13)]
    hist = merge_history({"2408": hist}, parse_revenue([ROW]), {"2408"})["2408"]
    rev = parse_revenue([ROW])["2408"]
    kinds = {e["kind"] for e in revenue_events("2408", "南亞科", rev, hist, 10)}
    assert kinds == {"turn_up", "accel", "new_high"}
    # 歷史不夠長時不判斷新高，也不判斷轉折
    assert {e["kind"] for e in revenue_events("2408", "南亞科", rev, [], 10)} == {"accel"}


def test_build_signals_light_and_price_note(tmp_path):
    (tmp_path / "chain_inputs.json").write_text(json.dumps(
        {"memory": [{"name": "DRAM 合約價", "trend": "up", "value": "v", "as_of": "2026-10", "url": "https://x"}]},
        ensure_ascii=False), "utf-8")
    sig = build_signals(config, {}, None, tmp_path, history_fn=fake_history,
                        revenue_fn=lambda: parse_revenue([ROW]))
    mem = next(c for c in sig["chains"] if c["id"] == "memory")
    assert mem["light"] == "轉強"            # 上游轉強＋營收加速
    assert mem["revenue"]["count"] == 1 and mem["revenue"]["avg_accel"] == 50.0
    airline = next(c for c in sig["chains"] if c["id"] == "airline")
    assert airline["upstream"][0]["auto"] and airline["upstream"][0]["trend"] in ("up", "flat", "down")
    assert mem["price"]["avg_1m"] is not None and mem["price"]["note"]
    ai = next(c for c in sig["chains"] if c["id"] == "ai_server")
    assert ai["light"] == "資料不足"
    assert "2408" in sig["revenue_history"]


def test_build_signals_reuses_previous_revenue_when_fetch_fails(tmp_path):
    first = build_signals(config, {}, None, tmp_path, revenue_fn=lambda: parse_revenue([ROW]))
    again = build_signals(config, {}, first, tmp_path, revenue_fn=lambda: {})
    assert again["revenue_latest"]["2408"]["yoy"] == 100.0


def test_briefing_includes_signals(tmp_path):
    from functools import partial
    from briefing.market import build_market
    from briefing.news import fetch_news
    from briefing.summarize import simple_summary
    b = build(tmp_path, market_fn=partial(build_market, history_fn=fake_history),
              news_fn=partial(fetch_news, parse=fake_parse), summary_fn=simple_summary)
    assert [c["id"] for c in b["signals"]["chains"]] == [c["id"] for c in config.CHAINS]
    assert len(config.CHAINS) >= 20


def test_market_input_trend_and_inverse():
    from briefing.signals import market_input
    q = {"chg_1m": 8.0, "last": 70.5, "as_of": "2026-11-07"}
    assert market_input({"symbol": "CL=F", "name": "原油"}, q, 5)["trend"] == "up"
    assert market_input({"symbol": "CL=F", "name": "原油", "inverse": True}, q, 5)["trend"] == "down"
    assert market_input({"symbol": "CL=F", "name": "原油"}, {**q, "chg_1m": 2.0}, 5)["trend"] == "flat"
    assert market_input({"symbol": "X", "name": "x"}, None, 5)["trend"] is None


def test_themes_validation():
    good = {"title": "雲端上修資本支出", "chain": "AI 伺服器", "reasoning": "r", "watch": ["廣達 2382"],
            "counter": "c", "priced_in": "p"}
    assert validate({**_ai(), "themes": [good]}) == []
    assert any("counter" in p for p in validate({**_ai(), "themes": [{**good, "counter": ""}]}))
    assert any("watch" in p for p in validate({**_ai(), "themes": [{**good, "watch": []}]}))
    assert any("1 到 3" in p for p in validate({**_ai(), "themes": [good] * 4}))


def test_revenue_alerts_once_per_month(tmp_path):
    ev = [{"key": "rev:2408:2026-10:accel", "kind": "accel", "text": "🚀 南亞科"},
          {"key": "rev:2408:2026-10:decel", "kind": "decel", "text": "x"}]
    rules = {"revenue": {"enabled": True, "kinds": ["accel"]}}
    alerts, state = evaluate(rules, {}, [], {}, "d", ev)
    assert [a["key"] for a in alerts] == ["rev:2408:2026-10:accel"]
    assert evaluate(rules, {}, [], state, "d2", ev)[0] == []
    assert evaluate({"revenue": {"enabled": False}}, {}, [], {}, "d", ev)[0] == []

    (tmp_path / "latest.json").write_text(json.dumps({"signals": {"revenue_events": ev}}), "utf-8")
    sent = []
    from datetime import datetime, timedelta, timezone
    out = run_check(rules, tmp_path / "s.json", datetime(2026, 11, 10, tzinfo=timezone(timedelta(hours=8))),
                    quotes_fn=lambda s: {}, deliver_fn=lambda t, s: sent.append(t) or ["line"], data_dir=tmp_path)
    assert len(out) == 1 and "南亞科" in sent[0]
