"""回測：用假資料跑兩個區間，檢查不偷看未來、輸出格式。"""
import random

from papertrade import backtest as bt
from tests.test_papertrade import TW, fake_get, fake_px
from datetime import datetime


def fake_get_bt(url):
    if "finmindtrade" in url:
        code = url.split("data_id=")[1].split("&")[0]
        rnd = random.Random(code)
        if "MonthRevenue" in url:
            rows = []
            for y in (2024, 2025, 2026):
                for m in range(1, 13):
                    if (y, m) <= (2026, 10):
                        rows.append({"revenue_year": y, "revenue_month": m, "revenue": 1000 * (1 + rnd.random()) * (1.1 ** (y - 2024))})
            return {"data": rows}
        return {"data": [{"date": f"2026-{m:02d}-{d:02d}", "PER": 8 + rnd.random() * 20, "PBR": 0.8 + rnd.random(),
                          "dividend_yield": 2 + rnd.random() * 4} for m in range(4, 12) for d in (1, 15)]}
    return fake_get(url)


def test_revenue_availability_no_lookahead():
    s = {"2025-09": 100.0, "2026-08": 150.0, "2026-09": 200.0, "2025-08": 100.0}
    assert bt.revenue_on(s, "2026-10-10")["ym"] == "2026-08"   # 9 月營收 10/11 才算知道
    assert bt.revenue_on(s, "2026-10-11")["ym"] == "2026-09"
    assert bt.revenue_on(s, "2026-10-11")["yoy"] == 100.0


def test_backtest_runs_two_windows(tmp_path, monkeypatch):
    monkeypatch.setattr(bt.time, "sleep", lambda s: None)
    monkeypatch.setattr(bt, "WINDOWS", [(8, "近 8 天", 0), (15, "近 15 天", 0), (10, "更早 10 天", 15)])
    now = datetime(2026, 11, 10, 19, tzinfo=TW)
    out = bt.main(["--out", str(tmp_path)], get=fake_get_bt, history_fn=lambda s: fake_px(s, "2026-11-10"), now=now)
    assert [w["label"] for w in out["windows"]] == ["近 8 天", "近 15 天", "更早 10 天"]
    assert out["windows"][2]["unseen"] and out["windows"][2]["end"] < out["windows"][1]["start"]
    assert "claude2" in out["windows"][1]["win"]
    w = out["windows"][1]
    assert w["days"] == 15 and w["end"] == "2026-11-10"
    ids = {m["id"] for m in w["methods"]}
    assert "ai_theme" not in ids and "claude" in ids
    assert len(w["benchmarks"]["^TWII"]["equity"]) == 15
    assert w["claude_trades"] and all(t["reason"] for t in w["claude_trades"])
    assert out["coverage"]["revenue"] > 0
    from papertrade import config as C
    assert any(m["id"] == "ai_theme" for m in C.METHODS) and C.TRADING_DAYS == 30  # 回測後設定有還原
