import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest

from holdings import config
from holdings.__main__ import build
from holdings.analyze import SCHEMA, analyze, build_prompt
from holdings.calc import beta, max_drawdown, value_positions
from holdings.model import Position, load_positions, load_transactions

from tests.fakes_holdings import FakeClient, fake_history

EX = Path(__file__).parent.parent / "holdings" / "examples"
NOW = datetime(2026, 11, 7, 8, 0, tzinfo=timezone(timedelta(hours=8)))


def test_position_infers_market_and_quote_symbol():
    assert Position("2330", 1, 1).quote_symbol == "2330.TW"
    assert Position("6488.TWO", 1, 1).quote_symbol == "6488.TWO"
    p = Position("nvda", 1, 1)
    assert (p.symbol, p.market, p.currency, p.quote_symbol) == ("NVDA", "US", "USD", "NVDA")
    assert Position("00878", 1, 1).market == "TW"


def test_load_chinese_headers_and_bom(tmp_path):
    f = tmp_path / "h.csv"
    f.write_text("﻿代號,股數,成本,買入日期\n2330,\"1,000\",850,2025/03/12\n\n", "utf-8")
    [p] = load_positions(f)
    assert p.shares == 1000 and p.buy_date == date(2025, 3, 12) and p.account == "未指定"


def test_load_reports_bad_line(tmp_path):
    f = tmp_path / "h.csv"
    f.write_text("代號,股數,成本\n2330,,850\n", "utf-8")
    with pytest.raises(ValueError, match="第 2 行"):
        load_positions(f)


def test_value_twd_and_fx_split():
    hist = fake_history(["2330.TW", "NVDA", "USDTWD=X"])
    rows, warn = value_positions([Position("2330", 1000, 850), Position("NVDA", 50, 120, fx_cost=30.0)],
                                 hist, config, date(2026, 11, 7))
    tw, us = rows
    assert tw["value_twd"] == 1_000_000 and tw["pnl_twd"] == 150_000 and tw["return_pct"] == 17.65
    # NVDA：市值 50*180*32 = 288,000；成本 50*120*30 = 180,000
    assert us["value_twd"] == 288_000 and us["cost_twd"] == 180_000
    assert us["pnl_from_price_twd"] == 50 * 60 * 30 and us["pnl_from_fx_twd"] == 50 * 180 * 2
    assert us["pnl_from_price_twd"] + us["pnl_from_fx_twd"] == us["pnl_twd"]
    assert not warn


def test_missing_quote_is_flagged_not_counted():
    rows, warn = value_positions([Position("9999", 1, 1)], fake_history(["USDTWD=X"]), config, date(2026, 11, 7))
    assert rows[0]["error"] and "9999" in warn[0]


def test_annualized_only_after_min_days():
    hist = fake_history(["2330.TW"])
    short, long_ = value_positions([Position("2330", 1, 500, buy_date=date(2026, 10, 1)),
                                    Position("2330", 1, 500, buy_date=date(2024, 11, 7))], hist, config, date(2026, 11, 7))[0]
    assert short["annualized_pct"] is None
    assert long_["annualized_pct"] == pytest.approx(41.42, abs=0.1)  # 兩年翻倍 ≈ 年化 41%


def test_beta_and_drawdown():
    xs = [0.01, -0.02, 0.015] * 10
    assert beta(xs, [2 * x for x in xs]) == pytest.approx(2)
    assert max_drawdown([100, 120, 90, 130]) == pytest.approx(-0.25)


def test_build_example_end_to_end(tmp_path):
    client = FakeClient()
    rep = build(EX / "holdings.example.csv", tmp_path, history_fn=fake_history,
                analyze_fn=lambda r, b: analyze(r, b, client=client),
                tx_csv=EX / "transactions.example.csv", briefing_json=tmp_path / "none.json", now=NOW)
    t, a = rep["totals"], rep["allocation"]
    assert t["positions"] == 5 and t["value_twd"] == sum(r["value_twd"] for r in rep["positions"])
    assert sum(g["weight_pct"] for g in a["by_symbol"]) == pytest.approx(100, abs=0.05)
    assert "2330" in a["concentration"]["over_limit"]
    assert a["by_sector"][0]["key"] == "半導體" and a["by_sector"][0]["over_limit"]
    assert t["realized_twd"] == 1000 * 60 - 450
    assert t["dividends_this_year_twd"] == pytest.approx(4500 + 16.6 * 32, rel=0.01)  # 用配息日的匯率
    assert {s["name"] for s in rep["risk"]["scenarios"]} == {s["name"] for s in config.SCENARIOS}
    assert rep["risk"]["beta"] is not None and rep["risk"]["max_drawdown_pct"] <= 0
    # Claude：只留真實存在的代號、不送帳戶與金額
    assert [p["symbol"] for p in rep["analysis"]["positions"]] == ["2330"]
    prompt = client.calls[0]["messages"][0]["content"]
    assert "永豐" not in prompt and "複委託" not in prompt and "1,000,000" not in prompt
    assert client.calls[0]["output_config"]["format"]["schema"] is SCHEMA
    assert json.loads((tmp_path / "holdings.json").read_text("utf-8"))["totals"] == t


def test_ai_failure_keeps_previous_analysis(tmp_path):
    kw = dict(history_fn=fake_history, briefing_json=tmp_path / "none.json", tx_csv=tmp_path / "none.csv", now=NOW)
    ok = build(EX / "holdings.example.csv", tmp_path, analyze_fn=lambda r, b: analyze(r, b, client=FakeClient()), **kw)

    def boom(r, b):
        raise RuntimeError("down")
    again = build(EX / "holdings.example.csv", tmp_path, analyze_fn=boom, **kw)
    assert again["analysis"]["headline"] == ok["analysis"]["headline"]
    assert any("AI 分析" in w for w in again["warnings"])


def test_refuses_when_no_quotes(tmp_path):
    with pytest.raises(RuntimeError):
        build(EX / "holdings.example.csv", tmp_path, history_fn=lambda s: {}, use_ai=False, now=NOW)


def test_prompt_includes_briefing_points(tmp_path):
    rep = build(EX / "holdings.example.csv", tmp_path, history_fn=fake_history, use_ai=False,
                tx_csv=tmp_path / "none.csv", now=NOW)
    p = build_prompt(rep, {"summary": {"points": [{"tag": "企業", "title": "台積電營收創高", "summary": "AI 需求"}]}})
    assert "台積電營收創高" in p and "未填" not in p


# ---------- Supabase 模式 ----------
import io  # noqa: E402

from holdings.__main__ import build_store  # noqa: E402
from holdings.store import SupabaseStore  # noqa: E402


class FakeOpener:
    """模擬 Supabase REST API。"""

    def __init__(self, holdings, transactions=(), reports=()):
        self.data = {"holdings": list(holdings), "transactions": list(transactions), "holdings_reports": list(reports)}
        self.requests = []

    def __call__(self, req, timeout=None):
        self.requests.append(req)
        table = req.full_url.split("/rest/v1/")[1].split("?")[0]
        body = b""
        if req.get_method() == "GET":
            body = json.dumps(self.data[table]).encode()
        else:
            self.data[table] = json.loads(req.data)
        return io.BytesIO(body)


def _row(uid, **kw):
    return {"id": 1, "user_id": uid, "name": "", "account": "", "sector": "", "thesis": "",
            "buy_date": None, "fx_cost": None, **kw}


def test_supabase_store_builds_report_per_user():
    op = FakeOpener([
        _row("u1", symbol="2330", shares=1000, avg_cost=850, buy_date="2025-03-12"),
        _row("u1", symbol="NVDA", shares="50", avg_cost="120", fx_cost=30),
        _row("u1", symbol="BAD", shares=None, avg_cost=1),
        _row("u2", symbol="0050", shares=10, avg_cost=150),
    ], transactions=[{"user_id": "u1", "date": "2026-07-17", "symbol": "2330", "type": "dividend", "amount": 4500}])
    store = SupabaseStore("https://x.supabase.co/", "sb_secret_abc", opener=op)
    res = build_store(store, history_fn=fake_history, use_ai=False, briefing_json=Path("none.json"), now=NOW)
    assert set(res) == {"u1", "u2"}
    assert res["u1"]["totals"]["positions"] == 2 and res["u1"]["totals"]["dividends_twd"] == 4500
    assert any("BAD" in w for w in res["u1"]["warnings"])
    saved = op.data["holdings_reports"]
    assert saved[0]["user_id"] == "u2" and saved[0]["report"]["totals"]["positions"] == 1
    post = op.requests[-1]
    assert post.get_method() == "POST" and "on_conflict=user_id" in post.full_url
    assert post.headers["Apikey"] == "sb_secret_abc" and "Authorization" not in post.headers
    assert "merge-duplicates" in post.headers["Prefer"]


def test_supabase_keeps_previous_analysis_without_ai():
    prev = {"analysis": {"headline": "上次的分析", "generated_at": "2026-11-06T08:00"}}
    op = FakeOpener([_row("u1", symbol="2330", shares=1, avg_cost=1)], reports=[{"user_id": "u1", "report": prev}])
    store = SupabaseStore("https://x.supabase.co", "eyJlegacy", opener=op)
    res = build_store(store, history_fn=fake_history, use_ai=False, now=NOW)
    assert res["u1"]["analysis"]["headline"] == "上次的分析"
    assert op.requests[0].headers["Authorization"] == "Bearer eyJlegacy"


def test_supabase_empty_db_is_fine():
    assert build_store(SupabaseStore("https://x", "k", opener=FakeOpener([])), history_fn=fake_history) == {}


def test_edge_store_uses_actions_oidc(monkeypatch):
    from holdings.store import EdgeStore, store_from_env
    calls = []

    def opener(req, timeout=None):
        calls.append(req)
        if "idtoken" in req.full_url:
            assert "audience=invest-assistant-holdings" in req.full_url
            return io.BytesIO(b'{"value": "OIDC"}')
        if req.get_method() == "GET":
            return io.BytesIO(json.dumps({"holdings": [_row("u1", symbol="2330", shares=1, avg_cost=1)],
                                          "transactions": [], "reports": []}).encode())
        return io.BytesIO(b'{"saved": 1}')

    monkeypatch.delenv("SUPABASE_SECRET_KEY", raising=False)
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.setenv("ACTIONS_ID_TOKEN_REQUEST_URL", "https://gh/idtoken?x=1")
    monkeypatch.setenv("ACTIONS_ID_TOKEN_REQUEST_TOKEN", "rt")
    store = EdgeStore.from_actions("https://p.supabase.co/", opener=opener)
    res = build_store(store, history_fn=fake_history, use_ai=False, now=NOW)
    assert res["u1"]["totals"]["positions"] == 1
    assert calls[1].full_url == "https://p.supabase.co/functions/v1/holdings-sync"
    assert calls[1].headers["Authorization"] == "Bearer OIDC"
    assert calls[-1].get_method() == "POST" and json.loads(calls[-1].data)["user_id"] == "u1"
    monkeypatch.setenv("SUPABASE_SECRET_KEY", "sb_secret_x")
    assert isinstance(store_from_env("https://p.supabase.co"), SupabaseStore)
