import json
from datetime import datetime, timedelta, timezone

from alerts import channels, render
from alerts.__main__ import deliver, fetch_quotes, main, run_check
from alerts.check import evaluate
from briefing import config
from briefing.market import build_market

from tests.fakes import fake_history

TW = timezone(timedelta(hours=8))
Q = {"last": 1500.0, "change_pct": 3.4, "high_52w": 1500.0, "low_52w": 900.0, "name": "台積電"}


def test_price_rules_fire_once_per_day():
    rules = {"price": [{"symbol": "2330.TW", "name": "台積電", "above": 1450, "below": 1000,
                        "move_pct": 3, "new_52w": True}]}
    alerts, state = evaluate(rules, {"2330.TW": Q}, [], {}, "2026-11-07")
    keys = {a["key"] for a in alerts}
    assert keys == {"2330.TW:above", "2330.TW:move_up", "2330.TW:high_52w"}
    again, state2 = evaluate(rules, {"2330.TW": Q}, [], state, "2026-11-07")
    assert again == []
    nextday, _ = evaluate(rules, {"2330.TW": Q}, [], state2, "2026-11-08")
    assert len(nextday) == 3


def test_move_below_threshold_and_missing_quote_are_quiet():
    rules = {"price": [{"symbol": "A", "move_pct": 5}, {"symbol": "B", "move_pct": 1}]}
    alerts, _ = evaluate(rules, {"A": {**Q, "change_pct": -4.9}, "B": {"error": "x"}}, [], {}, "d")
    assert alerts == []
    alerts, _ = evaluate(rules, {"A": {**Q, "change_pct": -5.2}}, [], {}, "d")
    assert alerts[0]["key"] == "A:move_down" and "大跌" in alerts[0]["text"]


def test_event_keywords_and_dedup():
    rules = {"events": [{"name": "Fed", "keywords": ["FOMC", "台積電 營收"]}]}
    news = [{"title": "fomc 會議紀要：多數官員支持暫停", "url": "u1", "source": "s"},
            {"title": "台積電 10 月營收創新高", "url": "u2", "source": "s"},
            {"title": "台積電 擴廠", "url": "u3", "source": "s"}]
    alerts, state = evaluate(rules, {}, news, {}, "d")
    assert [a["url"] for a in alerts] == ["u1", "u2"]
    again, _ = evaluate(rules, {}, news, state, "d")
    assert again == []


def test_run_check_primes_news_on_first_run_and_saves_state(tmp_path):
    rules = {"price": [{"symbol": "X", "move_pct": 1}],
             "events": [{"name": "Fed", "keywords": ["FOMC"]}]}
    sent = []
    state = tmp_path / "s.json"
    now = datetime(2026, 11, 7, 10, 0, tzinfo=TW)
    news = [{"title": "FOMC 舊聞", "url": "old"}]
    kw = dict(quotes_fn=lambda s: {"X": {**Q, "change_pct": 2}}, deliver_fn=lambda t, s: sent.append(t) or ["line"])
    alerts = run_check(rules, state, now, news_fn=lambda: news, **kw)
    assert [a["kind"] for a in alerts] == ["price"]  # 舊新聞不轟炸
    news.append({"title": "FOMC 新消息", "url": "new"})
    alerts = run_check(rules, state, now, news_fn=lambda: news, **kw)
    assert [a["url"] for a in alerts] == ["new"]
    assert len(sent) == 2 and json.loads(state.read_text("utf-8"))["primed"]


def test_news_failure_still_checks_prices(tmp_path):
    def boom():
        raise OSError("down")
    alerts = run_check({"price": [{"symbol": "X", "move_pct": 1}], "events": [{"name": "e", "keywords": ["a"]}]},
                       tmp_path / "s.json", datetime.now(TW), quotes_fn=lambda s: {"X": Q},
                       news_fn=boom, deliver_fn=lambda t, s: ["line"])
    assert len(alerts) == 1


def test_fetch_quotes_uses_compute_quote():
    q = fetch_quotes(["NVDA", "MISSING"], history_fn=lambda s: fake_history([x for x in s if x != "MISSING"]))
    assert set(q) == {"NVDA"} and {"last", "change_pct", "high_52w"} <= set(q["NVDA"])


def test_line_push_and_broadcast(monkeypatch):
    calls = []
    post = lambda url, token, payload: calls.append((url, token, payload))
    monkeypatch.delenv("LINE_CHANNEL_TOKEN", raising=False)
    assert channels.send_line("hi", post=post) is False and calls == []
    monkeypatch.setenv("LINE_CHANNEL_TOKEN", "tok")
    monkeypatch.setenv("LINE_TO", "U123")
    assert channels.send_line("hi", post=post)
    assert calls[-1][0].endswith("/push") and calls[-1][2]["to"] == "U123"
    monkeypatch.delenv("LINE_TO")
    channels.send_line("hi", post=post)
    assert calls[-1][0].endswith("/broadcast") and "to" not in calls[-1][2]


def test_split_text_respects_limit():
    text = "\n".join(["一二三四五"] * 3000)
    parts = channels.split_text(text, limit=5000)
    assert all(len(p) <= 5000 for p in parts) and "".join(parts).count("一") == 3000


def test_deliver_one_channel_failing_does_not_stop_other():
    def bad(t):
        raise RuntimeError("line down")
    assert deliver("t", "s", line=bad, email=lambda s, b: True) == ["email"]


def test_brief_text_from_real_brief_shape():
    market = build_market(config, history_fn=fake_history)
    brief = {"generated_at": "2026-11-07T07:30+08:00", "market": market, "warnings": ["w"],
             "summary": {"headline": "今日重點", "points": [{"tag": "央行", "title": "Fed", "summary": "說明"}]}}
    t = render.brief_text(brief)
    assert t.startswith("📰 投資早報 2026-11-07 07:30") and "台股加權指數" in t and "1. [央行] Fed" in t
    assert "⚠ w" in t and len(t) < 5000


def test_cli_brief_dry_run(tmp_path, capsys):
    (tmp_path / "latest.json").write_text(json.dumps({"generated_at": "2026-11-07T07:30", "market": {},
                                                      "summary": {"headline": "H"}}), "utf-8")
    assert main(["brief", "--data", str(tmp_path), "--dry-run"]) == 0
    assert "H" in capsys.readouterr().out


def test_default_rules_file_is_valid():
    from alerts.__main__ import HERE
    rules = json.loads((HERE / "rules.json").read_text("utf-8"))
    assert all("symbol" in r for r in rules["price"]) and all(e["keywords"] for e in rules["events"])
