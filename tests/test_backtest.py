from briefing import backtest


def _sig(light, price, bench=100.0):
    return {"chains": [{"id": "m", "name": "記憶體", "light": light,
                        "stocks": [{"symbol": "A", "last": price}, {"symbol": "B", "last": price}],
                        "price": {"bench": "^SOX", "bench_last": bench}}]}


def test_log_one_entry_per_date_and_keep_order():
    log = backtest.update_log([], "2026-11-06", _sig("轉強", 10))
    log = backtest.update_log(log, "2026-11-05", _sig("持平", 9))
    log = backtest.update_log(log, "2026-11-06", _sig("轉弱", 11))  # 同一天以最後一次為準
    assert [e["date"] for e in log] == ["2026-11-05", "2026-11-06"]
    assert log[-1]["chains"]["m"]["light"] == "轉弱"


def test_evaluate_excess_hit_rate_and_changes():
    log = []
    # 前 5 天轉強，股價每天 +2%，指數不動 → 5 天後超額報酬為正
    for i in range(10):
        light = "轉強" if i < 5 else "轉弱"
        log = backtest.update_log(log, f"2026-10-{i + 10:02d}", _sig(light, 100 * 1.02 ** i))
    r = backtest.evaluate(log, {"m": "記憶體"})
    week = r["horizons"]["1 週"]
    assert week["轉強"]["n"] == 5 and week["轉強"]["hit"] == 100.0 and week["轉強"]["avg_excess"] > 0
    assert week["轉弱"]["n"] == 0
    assert r["horizons"]["1 個月"]["轉強"]["n"] == 0
    assert r["days_logged"] == 10 and r["since"] == "2026-10-10"
    ch = r["changes"][0]
    assert (ch["from"], ch["to"], ch["name"]) == ("轉強", "轉弱", "記憶體") and ch["excess_since"] > 0


def test_benchmark_change_or_missing_price_is_skipped():
    a = backtest.snapshot(_sig("轉強", 10))["m"]
    b = backtest.snapshot(_sig("轉強", 11))["m"]
    assert backtest._ret(a, {**b, "bench": "^TWII"}) is None
    assert backtest._ret(a, {**b, "prices": {}}) is None


def test_run_writes_file(tmp_path):
    out = backtest.run(tmp_path, "2026-11-06", _sig("轉強", 10))
    assert (tmp_path / backtest.LOG_FILE).exists() and out["days_logged"] == 1
    assert backtest.run(tmp_path, "2026-11-06", None) is None
