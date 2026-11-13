"""研究框架：保留段不外洩、VIX 延後一天、股利入帳、快速路徑等價、分折、試驗紀錄、請求檔檢查。全部用合成資料。"""
import copy
import json
import urllib.error
from datetime import datetime

import pytest

pytest.importorskip("papertrade.metrics")

from papertrade import __main__ as pm  # noqa: E402
from papertrade import backtest as bt  # noqa: E402
from papertrade import config as C  # noqa: E402
from papertrade import engine, methods  # noqa: E402
from papertrade.research import __main__ as cli  # noqa: E402
from papertrade.research import dataset, report, request, runner, synthetic  # noqa: E402

CODES = list(pm.universe()[0])[:14]
UNI = synthetic.sub_universe(CODES)
N_DAYS = 420


def make(n_days=N_DAYS):
    """合成資料：3 月除息（落在樣本內），大盤從第 300 天起走跌（樣本內會跌破年線）。"""
    d = synthetic.make_dataset(n_days=n_days, codes=CODES, seed=1, div_month="03")
    tw = d["px"]["^TWII"]
    for f in ("open", "close", "adj_close"):
        tw[f] = [round(x * 0.997 ** max(0, i - 300), 2) for i, x in enumerate(tw[f])]
    return d


@pytest.fixture(scope="module")
def full():
    return make()


@pytest.fixture(scope="module")
def parts(full):
    b = dataset.boundary(bt.calendar(full["px"]))
    ins, hold = dataset.split_dataset(full, b["holdout_start"])
    return b, ins, hold


@pytest.fixture(scope="module")
def baseline(parts):
    b, ins, _ = parts
    return runner.run_variant("baseline", ins, {**b, "insample_sha256": "x" * 64}, uni=UNI)


# ---------- 假的網路來源 ----------

def fake_download(full, fail=()):
    import pandas as pd

    def download(symbols, start, end):
        cols = {}
        for sym in symbols:
            s = full["px"].get(sym)
            if s is None or sym in fail:
                continue
            idx = pd.to_datetime(s["dates"])
            for name, key in (("Open", "open"), ("Close", "close"), ("Adj Close", "adj_close"), ("Volume", "volume"),
                              ("Dividends", "div"), ("Stock Splits", "split")):
                cols[(sym, name)] = pd.Series(s[key], index=idx, dtype=float)
        df = pd.DataFrame(cols)
        df = df[(df.index >= start) & (df.index < end)]
        for sym in fail:   # yfinance 抓不到時該代號整欄是空值
            df[(sym, "Open")] = df[(sym, "Close")] = df[(sym, "Volume")] = float("nan")
        return df
    return download


def fake_get(full, calls=None):
    def get(url):
        if calls is not None:
            calls.append(url)
        if "finmindtrade" in url:
            code = url.split("data_id=")[1].split("&")[0]
            if "MonthRevenue" in url:
                return {"data": [{"revenue_year": int(ym[:4]), "revenue_month": int(ym[5:]), "revenue": v}
                                 for ym, v in full["rev"][code].items()]}
            col = full["val"][code]
            return {"data": [{"date": d, "PER": col["pe"][i], "PBR": col["pb"][i], "dividend_yield": col["dy"][i]}
                             for i, d in enumerate(col["dates"])]}
        if "T86" in url:
            raw = url.split("date=")[1][:8]
            rows = full["chips"].get(f"{raw[:4]}-{raw[4:6]}-{raw[6:]}") or {}
            return {"stat": "OK", "fields": ["證券代號", "證券名稱", "外陸資買賣超股數(不含外資自營商)", "投信買賣超股數"],
                    "data": [[c, "x", f"{r['foreign']:,}", str(r["trust"])] for c, r in rows.items()] + [["9999", "池外", "1", "1"]]}
        raise OSError("offline")
    return get


def do_fetch(tmp_path, full, **kw):
    last = bt.calendar(full["px"])[-1]
    now = datetime.fromisoformat(last).replace(hour=19, tzinfo=pm.TW)
    kw.setdefault("get", fake_get(full))
    return dataset.fetch(tmp_path, now=now, download=fake_download(full, kw.pop("fail", ())), sleep=lambda s: None,
                         universe_fn=lambda: UNI, **kw)


# ---------- 保留段 ----------

def test_boundary_is_last_20_percent_of_evaluation_days(full):
    cal = bt.calendar(full["px"])
    b = dataset.boundary(cal)
    assert b["warmup_end"] == cal[259] and b["insample_start"] == cal[260]
    assert b["n_eval"] == N_DAYS - 260 == b["n_insample"] + b["n_holdout"]
    assert b["n_holdout"] == 32 and b["holdout_start"] == cal[-32] and b["holdout_end"] == cal[-1]
    assert b["insample_end"] == cal[-33]


def test_split_removes_everything_on_or_after_holdout_start(full, parts):
    b, ins, hold = parts
    hs = b["holdout_start"]
    assert dataset.leaks(full, hs) and not dataset.leaks(ins, hs)
    for s in ins["px"].values():
        assert max(s["dates"]) < hs and len({len(v) for v in s.values()}) == 1   # 每個欄位（含 div、adj_close）一起截斷
    assert max(ins["px"]["^VIX"]["dates"]) < hs
    assert all(max(col["dates"]) < hs for col in ins["val"].values())
    assert ins["chips"] and max(ins["chips"]) < hs and min(hold["chips"]) >= hs
    # 月營收以「可用日」截斷：營收月份早於界線、但公布日在界線之後的，也不能留在樣本內
    late = [ym for ym in full["rev"][CODES[0]] if ym <= hs[:7] and bt._avail(ym) >= hs]
    assert late and all(ym not in ins["rev"][CODES[0]] for ym in late)
    assert all(bt._avail(ym) < hs for series in ins["rev"].values() for ym in series)
    assert all(min(s["dates"]) >= hs for s in hold["px"].values())


def test_adj_close_is_rebased_so_holdout_dividends_do_not_leak(full, parts):
    b, ins, hold = parts
    sym = next(s for s, k in hold["adj_scale"].items() if abs(k - 1) > 1e-6)   # 保留段有配息的股票
    a, raw = ins["px"][sym], full["px"][sym]
    assert a["adj_close"][-1] == a["close"][-1] and raw["adj_close"][len(a["dates"]) - 1] != raw["close"][len(a["dates"]) - 1]
    assert a["adj_close"][-1] / a["adj_close"][0] == pytest.approx(raw["adj_close"][len(a["dates"]) - 1] / raw["adj_close"][0], rel=1e-4)
    merged = dataset.merge_dataset(ins, hold)
    assert merged["px"][sym]["dates"] == raw["dates"] and merged["px"][sym]["close"] == raw["close"]
    assert merged["px"][sym]["adj_close"] == pytest.approx(raw["adj_close"], abs=2e-4)
    assert merged["rev"] == full["rev"] and merged["val"] == full["val"] and merged["chips"] == full["chips"]


def test_fetch_writes_only_insample_and_keeps_boundary_on_refetch(tmp_path, full):
    calls = []
    m = do_fetch(tmp_path, full, get=fake_get(full, calls), fail=("0050.TW",))
    hs = m["holdout_start"]
    assert not (tmp_path / dataset.HOLDOUT).exists() and m["holdout_written"] is False
    assert m["failed_symbols"] == ["0050.TW"] and m["counts"]["revenue"] == len(CODES) == m["counts"]["value"]
    ins = dataset.read_gz(tmp_path / dataset.INSAMPLE)
    assert not dataset.leaks(ins, hs) and "0050.TW" not in ins["px"]
    assert set(ins["px"][UNI[0][CODES[0]]]) == {"dates", *dataset.PX_FIELDS}
    assert any(x for s in ins["px"].values() for x in s["div"])
    # 法人：只抓樣本內的日子、只留選股池代號、每天一個快取檔
    t86 = [u for u in calls if "T86" in u]
    assert t86 and all(u.split("date=")[1][:8] < hs.replace("-", "") for u in t86)
    assert all("9999" not in rows for rows in ins["chips"].values())
    cached = sorted(p.stem for p in (tmp_path / dataset.CHIPS_DIR).glob("*.json"))
    assert cached == sorted(ins["chips"]) and max(cached) < hs
    assert json.loads((tmp_path / dataset.MANIFEST).read_text("utf-8"))["holdout_start"] == hs

    # 過一陣子重抓：資料變長，但界線不動；已有快取的日子不再連證交所
    longer = make(N_DAYS + 40)
    calls2 = []
    m2 = do_fetch(tmp_path, longer, get=fake_get(longer, calls2))
    assert m2["holdout_start"] == hs and m2["n_holdout"] == m["n_holdout"] + 40 and m2["insample_end"] == m["insample_end"]
    assert not [u for u in calls2 if "T86" in u]
    assert not dataset.leaks(dataset.read_gz(tmp_path / dataset.INSAMPLE), hs)
    assert dataset.boundary(bt.calendar(longer["px"]))["holdout_start"] > hs   # 沒有舊 manifest 的話界線會往後移


def test_fetch_skip_chips_and_chips_from(tmp_path, full):
    calls = []
    m = do_fetch(tmp_path / "a", full, get=fake_get(full, calls), skip_chips=True)
    assert m["counts"]["chip_days"] == 0 and not [u for u in calls if "T86" in u]
    cal = bt.calendar(full["px"])
    m = do_fetch(tmp_path / "b", full, chips_from=cal[300])
    assert min(dataset.read_gz(tmp_path / "b" / dataset.INSAMPLE)["chips"]) == cal[300]


def test_holdout_needs_flag_and_env(tmp_path, full):
    m = do_fetch(tmp_path, full, skip_chips=True)
    ok = {dataset.HOLDOUT_ENV: dataset.HOLDOUT_KEY}
    ds, _ = dataset.load_dataset(tmp_path, env=ok)   # 只有環境變數、沒有旗標：照樣只讀樣本內
    assert not dataset.leaks(ds, m["holdout_start"])
    with pytest.raises(dataset.HoldoutLocked):
        dataset.load_dataset(tmp_path, unlock_holdout=True, env={})
    with pytest.raises(dataset.HoldoutLocked):
        dataset.load_dataset(tmp_path, unlock_holdout=True, env={dataset.HOLDOUT_ENV: "yes"})
    with pytest.raises(FileNotFoundError, match="不存在"):
        dataset.load_dataset(tmp_path, unlock_holdout=True, env=ok)
    do_fetch(tmp_path, full, skip_chips=True, write_holdout=True)
    with pytest.raises(dataset.HoldoutLocked):   # 檔案在也一樣要兩個條件
        dataset.load_dataset(tmp_path, unlock_holdout=True, env={})
    ds, _ = dataset.load_dataset(tmp_path, unlock_holdout=True, env=ok)
    assert max(ds["px"]["^TWII"]["dates"]) == bt.calendar(full["px"])[-1]


def test_contaminated_insample_file_is_refused(tmp_path, full):
    do_fetch(tmp_path, full, skip_chips=True)
    dataset.write_gz(tmp_path / dataset.INSAMPLE, {**full, "chips": {}})
    with pytest.raises(RuntimeError, match="保留段"):
        dataset.load_dataset(tmp_path)


def test_synthetic_and_real_data_cannot_share_a_folder(tmp_path, full):
    do_fetch(tmp_path, full, skip_chips=True)
    with pytest.raises(RuntimeError, match="混用"):
        dataset.finalize(tmp_path, full, dataset.read_manifest(tmp_path), {"synthetic": True})


# ---------- 抓資料的重試 ----------

def test_retrying_backs_off_on_rate_limit():
    waits, n = [], {"k": 0}

    def get(url):
        n["k"] += 1
        if n["k"] <= 2:
            raise urllib.error.HTTPError(url, 402, "limit", {}, None)
        return {"data": [1]}
    assert dataset.retrying(get, sleep=waits.append)("u") == {"data": [1]} and waits == [60, 300]

    def always(url):
        raise urllib.error.HTTPError(url, 429, "limit", {}, None)
    waits.clear()
    g = dataset.retrying(always, sleep=waits.append, limit_budget=400)
    with pytest.raises(urllib.error.HTTPError):
        g("u")
    assert waits == [60, 300]   # 預算用完就不再等
    with pytest.raises(urllib.error.HTTPError):
        g("u2")
    assert waits == [60, 300]


def test_fetch_prices_retries_missing_symbols(full):
    n = {"k": 0}
    good = fake_download(full)

    def flaky(symbols, start, end):
        n["k"] += 1
        if n["k"] == 1:
            raise OSError("timeout")
        return good(symbols, start, end)
    px, failed = dataset.fetch_prices(["^TWII", "NOPE.TW"], "2018-01-01", "2030-01-01", download=flaky, sleep=lambda s: None)
    assert failed == ["NOPE.TW"] and px["^TWII"]["close"] == full["px"]["^TWII"]["close"] and n["k"] == 3


def test_fetch_chips_gives_up_after_consecutive_failures(tmp_path):
    calls = []

    def dead(url):
        calls.append(url)
        raise OSError("blocked")
    days = synthetic.weekdays("2020-01-01", 30)
    out, missing = dataset.fetch_chips(days, tmp_path, ["2330"], get=dead, sleep=lambda s: None, waits=(1,), max_fail=3)
    assert out == {} and missing == days and len(calls) == 3 * 2


# ---------- VIX 延後一天 ----------

def test_vix_before_is_strictly_earlier():
    s = {"dates": ["2026-01-05", "2026-01-06", "2026-01-07"], "close": [11.0, 22.0, 33.0]}
    assert bt.vix_before(s, "2026-01-06") == 11.0 and bt.vix_before(s, "2026-01-08") == 33.0
    assert bt.vix_before(s, "2026-01-05") is None and bt.vix_before(None, "2026-01-06") is None


def test_backtest_ctx_uses_previous_vix(full):
    cal = bt.calendar(full["px"])
    day = cal[300]
    px = pm.cut(full["px"], day)
    assert px["^VIX"]["dates"][-1] == day   # 同一個日曆日的 VIX 在資料裡，但不能用
    ctx = bt.day_ctx({"rev": {}, "val": {}, "chips": {}}, UNI[0], UNI[2], cal[:301], px)
    assert ctx["regime"]["vix"] == full["px"]["^VIX"]["close"][299] != full["px"]["^VIX"]["close"][300]


def test_research_run_sees_only_earlier_vix(parts, monkeypatch):
    b, ins, _ = parts
    seen = {}
    real = methods.METHOD_FNS["momentum"]
    monkeypatch.setitem(methods.METHOD_FNS, "momentum", lambda ctx: seen.setdefault(ctx["date"], ctx["regime"]["vix"]) and real(ctx))
    runner.simulate(ins, {}, b["warmup_end"], uni=UNI)
    vix = ins["px"]["^VIX"]
    assert len(seen) > 100
    for day, v in seen.items():
        i = vix["dates"].index(day)
        assert v == vix["close"][i - 1]


# ---------- 現金股利 ----------

def _div_case(div):
    days = ["2026-03-02", "2026-03-03", "2026-03-04", "2026-03-05"]
    s = {"dates": days, "open": [100.0, 100.0, 96.0, 97.0], "close": [100.0, 100.0, 97.0, 98.0], "volume": [1e6] * 4}
    if div is not None:
        s["div"] = div
    return days, {"A.TW": s}, {"A": "A.TW"}


def _advance(px, sym, days, decided):
    state = engine.new_state()
    acc = state["accounts"]["momentum"]
    acc["pending"] = {"decided": decided, "sells": [], "buys": [{"code": "A", "amount": 200_000, "reason": "測試"}]}
    state["last_decision"] = decided
    engine.advance(state, days, px, sym, {})
    return acc


def test_dividend_credited_on_ex_date_for_shares_held_before():
    days, px, sym = _div_case([0.0, 0.0, 2.5, 0.0])
    acc = _advance(px, sym, days, days[0])   # 3/3 開盤買進，3/4 除息
    shares = acc["positions"]["A"]["shares"]
    plain = _advance(*_div_case(None)[1:], days, days[0])
    assert shares == plain["positions"]["A"]["shares"] > 0
    assert acc["cash"] == pytest.approx(plain["cash"] + shares * 2.5)
    assert acc["dividends"] == pytest.approx(shares * 2.5) == acc["positions"]["A"]["div"]
    assert acc["equity"][-1]["equity"] - plain["equity"][-1]["equity"] == pytest.approx(shares * 2.5, abs=1)
    assert [e["equity"] for e in acc["equity"]][0] == plain["equity"][0]["equity"]   # 除息日之前完全相同


def test_no_dividend_when_bought_on_ex_date():
    days, px, sym = _div_case([0.0, 0.0, 2.5, 0.0])
    acc = _advance(px, sym, days, days[1])   # 3/4（除息日）開盤才買進
    assert acc["positions"]["A"]["date"] == days[2]
    assert "dividends" not in acc and "div" not in acc["positions"]["A"]


def test_dividend_step_is_inert_without_div_field():
    days, px, sym = _div_case(None)
    a = _advance(px, sym, days, days[0])
    b = _advance(*_div_case([0.0] * 4)[1:], days, days[0])
    assert a == b and "dividends" not in a


def test_dividend_paid_when_sold_at_open_of_ex_date():
    days, px, sym = _div_case([0.0, 0.0, 2.5, 0.0])
    state = engine.new_state()
    acc = state["accounts"]["momentum"]
    acc["positions"]["A"] = {"shares": 1000, "price": 100.0, "cost": 100_142.5, "date": days[0], "reason": "測試"}
    acc["pending"] = {"decided": days[1], "sells": [{"code": "A", "reason": "測試"}], "buys": []}
    state["last_decision"], state["start"] = days[1], days[0]
    engine.advance(state, days, px, sym, {})
    assert not acc["positions"] and acc["dividends"] == 2500.0


# ---------- 快速路徑和原本的路徑結果相同 ----------

def _rows(col):
    return [{"date": d, "PER": col["pe"][i], "PBR": col["pb"][i], "dividend_yield": col["dy"][i]} for i, d in enumerate(col["dates"])]


def _reference(ds, start_decision, uni):
    """原本回測的做法：cut() 複製全部歷史、revenue_on／value_on 逐日線性搜尋、不搬動 state。"""
    sym, names, chain_of = uni
    d = {**ds, "val": {c: _rows(col) for c, col in ds["val"].items()}}
    cal = bt.calendar(ds["px"])
    with runner.patched_config({}):
        state = engine.new_state()
        for i in range(cal.index(start_decision), len(cal)):
            dates = cal[:i + 1]
            px = pm.cut(ds["px"], cal[i])
            state = engine.run_day(state, bt.day_ctx(d, sym, chain_of, dates, px), dates, px, sym, names)
            state["checkpoint"] = None
    return state


def test_fast_path_matches_untruncated_path(parts, baseline):
    b, ins, _ = parts
    ref = _reference(ins, b["warmup_end"], UNI)
    full_hist = runner.simulate(ins, {"lookback": None}, b["warmup_end"], uni=UNI)
    assert ref["days"] == baseline["dates"]
    n_trades = 0
    for mid in runner.METHOD_IDS:
        acc, m = ref["accounts"][mid], baseline["methods"][mid]
        assert [e["equity"] for e in acc["equity"]] == m["equity"] == full_hist["methods"][mid]["equity"]
        assert acc["trades"] == m["trades"] == full_hist["methods"][mid]["trades"]
        n_trades += len(m["trades"])
    assert n_trades > 50 and sum(1 for mid in runner.METHOD_IDS if baseline["methods"][mid]["trades"]) >= 4


def test_lookup_helpers_match_backtest(full):
    code = CODES[3]
    tables = runner.revenue_tables(full["rev"])
    rows = _rows(full["val"][code])
    for day in bt.calendar(full["px"])[::7]:
        assert runner.revenue_at(tables, code, day) == bt.revenue_on(full["rev"][code], day)
        assert runner.value_at(full["val"][code], day) == bt.value_on(rows, day)
    assert runner.value_at(full["val"][code], "2000-01-01") is None and runner.revenue_at(tables, "nope", "2020-01-01") is None


def test_lookback_covers_longest_method_window():
    assert runner.LOOKBACK >= 300 and runner.LOOKBACK > 253   # 12-1 動能要 253 根、歐尼爾 252 根、大盤年線 200 根


# ---------- 分折與績效 ----------

def test_folds_are_contiguous_and_equal():
    assert runner.folds(10, 5) == [(0, 2), (2, 4), (4, 6), (6, 8), (8, 10)]
    assert runner.folds(13, 5) == [(0, 3), (3, 6), (6, 9), (9, 11), (11, 13)]
    assert runner.folds(3, 5) == [(0, 1), (1, 2), (2, 3)]
    spans = runner.folds(1512, 5)
    assert spans[0][0] == 0 and spans[-1][1] == 1512 and all(a[1] == b[0] for a, b in zip(spans, spans[1:]))
    assert max(b - a for a, b in spans) - min(b - a for a, b in spans) <= 1


def test_result_structure_and_fold_metrics(parts, baseline):
    b, ins, _ = parts
    res = baseline
    assert res["dates"][0] == b["insample_start"] and res["dates"][-1] == b["insample_end"] and len(res["dates"]) == b["n_insample"]
    assert set(res["methods"]) == set(runner.METHOD_IDS) and "claude" not in res["methods"]
    assert [f["days"] for f in res["folds"]] == [26, 26, 26, 25, 25] and res["folds"][0]["start"] == b["insample_start"]
    assert set(res["benchmarks"]) == {"^TWII", "0050.TW:TR"}
    for m in res["methods"].values():
        assert len(m["folds"]) == 5 and len(m["equity"]) == len(res["dates"])
        for key in ("days", "total_return", "cagr", "vol", "sharpe", "max_drawdown", "calmar", "turnover", "n_trades", "fees",
                    "win_rate", "avg_positions", "avg_exposure", "stop_exits", "dividends", "exit_cost"):
            assert key in m["all"] and key in m["folds"][0]
        assert sum(f["n_trades"] for f in m["folds"]) == m["all"]["n_trades"] == len(m["trades"])
        assert sum(f["stop_exits"] for f in m["folds"]) == m["all"]["stop_exits"]
        assert 0 <= m["all"]["avg_exposure"] <= 1.05 and 0 <= m["all"]["avg_positions"] <= C.TOP_N
        # 各折連續相乘＝全期（期末持股的賣出成本只扣在最後一天）
        growth = 1.0
        for f in m["folds"]:
            growth *= 1 + f["total_return"]
        assert growth == pytest.approx(1 + m["all"]["total_return"], rel=1e-9)
        assert m["folds"][-1]["exit_cost"] == m["all"]["exit_cost"] and m["folds"][0]["exit_cost"] == 0
        assert m["all"]["total_return"] == pytest.approx((m["equity"][-1] - m["all"]["exit_cost"]) / C.START_CASH - 1)
    g = res["regime"]
    assert all(sum(f[k] for f in g["folds"]) == g["all"][k] for k in ("below_ma60", "below_ma200", "vix25"))
    assert any(m["all"]["exit_cost"] > 0 for m in res["methods"].values())
    json.dumps(report.copy_slim(res))   # 可以存成 JSON


def test_0050_benchmark_includes_dividends(parts):
    b, ins, _ = parts
    days = [d for d in bt.calendar(ins["px"]) if d > b["warmup_end"]]
    tr = runner.bench_curves(ins, b["warmup_end"], days)["0050.TW:TR"]["equity"]
    s = ins["px"]["0050.TW"]
    i0 = s["dates"].index(b["warmup_end"])
    paid = [x for x in s["div"][i0 + 1:] if x]
    assert paid and len(tr) == len(days) + 1
    assert tr[-1] / tr[0] > s["close"][-1] / s["close"][i0]
    nodiv = copy.deepcopy(ins)
    nodiv["px"]["0050.TW"]["div"] = [0.0] * len(s["div"])
    flat = runner.bench_curves(nodiv, b["warmup_end"], days)["0050.TW:TR"]["equity"]
    assert flat[-1] / flat[0] == pytest.approx(s["close"][-1] / s["close"][i0])


def test_dividends_reach_accounts_in_research_run(parts, baseline):
    b, ins, _ = parts
    assert sum(m["all"]["dividends"] for m in baseline["methods"].values()) > 0
    nodiv = copy.deepcopy(ins)
    for s in nodiv["px"].values():
        s.pop("div")
    plain = runner.simulate(nodiv, {}, b["warmup_end"], uni=UNI)
    assert all(not any(r["dividends"]) for r in plain["methods"].values())
    assert any(plain["methods"][mid]["equity"] != baseline["methods"][mid]["equity"] for mid in runner.METHOD_IDS)


# ---------- 變體 ----------

def test_variant_flags_and_config_overrides_reach_engine_and_methods(parts, baseline, monkeypatch):
    b, ins, _ = parts
    flags = {"methods": {"momentum": {"market_filter": 200}}, "probe": 7}
    monkeypatch.setitem(runner.VARIANTS, "_probe", flags)
    keep_methods = C.METHODS
    seen = {"ctx": set(), "state": set(), "cfg": set(), "ids": set()}
    real_fn, real_plan = methods.METHOD_FNS["momentum"], engine.plan_orders

    def fn(ctx):
        seen["ctx"].add(ctx["variant"].get("probe"))
        assert isinstance(ctx["memo"], dict)
        return real_fn(ctx)

    def plan(state, mid, *a, **k):
        seen["state"].add(state["variant"].get("probe"))
        seen["ids"].add(mid)
        seen["cfg"].add(next(m for m in C.METHODS if m["id"] == "momentum").get("market_filter"))
        return real_plan(state, mid, *a, **k)
    monkeypatch.setitem(methods.METHOD_FNS, "momentum", fn)
    monkeypatch.setattr(engine, "plan_orders", plan)
    res = runner.run_variant("_probe", ins, {**b, "insample_sha256": "x" * 64}, uni=UNI)
    assert seen == {"ctx": {7}, "state": {7}, "cfg": {200}, "ids": set(runner.METHOD_IDS)}
    assert res["flags"] == flags and res["hash"] == runner.variant_hash(flags) != baseline["hash"]
    # 設定有還原：原本的清單物件、沒有被改到、天數上限也回來了
    assert C.METHODS is keep_methods and C.TRADING_DAYS == 30
    assert "market_filter" not in next(m for m in C.METHODS if m["id"] == "momentum")
    assert {"claude", "claude2", "ai_theme"} <= {m["id"] for m in C.METHODS}
    # 年線濾網真的改變了動能帳戶，其他方法不受影響
    assert res["regime"]["all"]["below_ma200"] > 0
    assert res["methods"]["momentum"]["equity"] != baseline["methods"]["momentum"]["equity"]
    assert res["methods"]["graham"]["equity"] == baseline["methods"]["graham"]["equity"]


def test_config_restored_even_when_run_fails(parts, monkeypatch):
    b, ins, _ = parts
    keep = C.METHODS
    monkeypatch.setattr(engine, "run_day", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    with pytest.raises(RuntimeError):
        runner.simulate(ins, {"methods": {"graham": {"x": 1}}}, b["warmup_end"], uni=UNI)
    assert C.METHODS is keep and C.TRADING_DAYS == 30
    with pytest.raises(ValueError, match="不在研究範圍"):
        runner.simulate(ins, {"methods": {"claude": {"stop_loss": -5}}}, b["warmup_end"], uni=UNI)
    with pytest.raises(KeyError):
        runner.run_variant("nope", ins, b)
    assert list(runner.VARIANTS) == ["baseline"] and runner.VARIANTS["baseline"] == {}


# ---------- 試驗紀錄與比較 ----------

def _trial(h, sr, variant="v", dataset_id="d"):
    return {"variant": variant, "hash": h, "code": "c", "at": "t", "dataset": dataset_id, "sharpe": {"momentum": {"all": sr, "folds": []}}}


def test_trial_count_floor_and_distinct_hashes():
    assert report.REGISTERED_TRIALS == 12
    assert report.n_trials([]) == 12
    assert report.n_trials([_trial("a", 0.1), _trial("a", 0.2), _trial("b", 0.3)]) == 12   # 2 個不同旗標，未達下限
    many = [_trial(f"h{i}", 0.01 * i) for i in range(15)] + [_trial("h3", 0.5)]   # 重跑同一組旗標不多算
    assert report.n_trials(many) == 15


def test_var_trials_uses_latest_entry_per_hash_and_same_dataset():
    assert report.var_trials([], "momentum") is None and report.var_trials([_trial("a", 0.1)], "momentum") is None
    trials = [_trial("a", 0.9), _trial("a", 0.02), _trial("b", 0.04), _trial("c", 0.5, dataset_id="other")]
    assert report.var_trials(trials, "momentum", "d") == pytest.approx(0.0002)   # 0.02 與 0.04
    assert report.var_trials(trials, "graham", "d") is None


def test_log_trial_appends_every_run(tmp_path, baseline):
    path = tmp_path / "trials.json"
    report.log_trial(path, baseline)
    e = report.log_trial(path, baseline)
    rows = report.read_trials(path)
    assert len(rows) == 2 and rows[1] == e and report.n_trials(rows) == 12
    assert e["variant"] == "baseline" and e["hash"] == runner.variant_hash({}) and e["dataset"] == "x" * 16
    assert set(e["sharpe"]) == set(runner.METHOD_IDS) and len(e["sharpe"]["momentum"]["folds"]) == 5
    m = baseline["methods"]["momentum"]
    assert e["sharpe"]["momentum"]["all"] * 252 ** 0.5 == pytest.approx(m["all"]["sharpe"])   # 紀錄的是每期（每日）夏普


def test_compare_variant_against_baseline(parts, baseline, monkeypatch, tmp_path):
    b, ins, _ = parts
    monkeypatch.setitem(runner.VARIANTS, "_probe", {"methods": {"momentum": {"market_filter": 200}}})
    var = runner.run_variant("_probe", ins, {**b, "insample_sha256": "x" * 64}, uni=UNI)
    path = tmp_path / "trials.json"
    report.log_trial(path, baseline)
    cmp = report.compare(baseline, var, report.read_trials(path), n_boot=50)
    mom, gra = cmp["methods"]["momentum"], cmp["methods"]["graham"]
    assert mom["affected"] and not gra["affected"] and cmp["n_trials"] == 12
    assert gra["all"]["diff"]["sharpe"] == 0 and gra["overlap"] in (1.0, None)
    assert len(mom["folds"]) == 5 and set(mom["folds"][0]) == set(report.DIFF_KEYS) and mom["wins"]["of"] == 5
    assert mom["all"]["diff"]["cagr"] == pytest.approx(var["methods"]["momentum"]["all"]["cagr"] - baseline["methods"]["momentum"]["all"]["cagr"])
    assert mom["sharpe_diff_ci"]["ci_low"] <= mom["sharpe_diff_ci"]["ci_high"] and 0 <= mom["overlap"] <= 1
    assert mom["var_trials"] is None and "PSR" in mom["dsr_note"] and mom["dsr"]["sr0"] == 0.0   # 只有 1 筆紀錄：退回對 0 的 PSR
    report.log_trial(path, var)
    cmp2 = report.compare(baseline, var, report.read_trials(path), n_boot=50)
    assert cmp2["methods"]["momentum"]["var_trials"] > 0 and cmp2["methods"]["momentum"]["dsr"]["sr0"] > 0
    assert cmp2["methods"]["momentum"]["dsr"]["n_trials"] == 12 and not cmp2["methods"]["momentum"]["dsr_note"]
    md = report.compare_markdown(cmp2)
    assert "價格動能" in md and "Deflated Sharpe" in md and "葛拉漢價值" in md.split("##")[0]
    with pytest.raises(ValueError, match="資料集不同"):
        report.compare({**baseline, "dataset": "zzz"}, var, [])


# ---------- 請求檔 ----------

def test_request_whitelist(monkeypatch):
    monkeypatch.setitem(runner.VARIANTS, "M1", {"methods": {"momentum": {"market_filter": 200}}})
    v = request.validate
    assert v({"cmd": "fetch"}) == [["fetch"]]
    assert v({"cmd": "fetch", "args": ["--skip-chips", "--chips-from", "2019-01-02"]}) == [["fetch", "--skip-chips", "--chips-from", "2019-01-02"]]
    assert v({"cmd": "run", "variants": ["baseline", "M1"], "folds": 4, "note": "第一次"}) == [["run", "--variant", "baseline", "--variant", "M1", "--folds", "4"]]
    assert v({"cmd": "compare", "variant": "M1"}) == [["compare", "--base", "baseline", "--variant", "M1"]]
    assert v({"steps": [{"cmd": "fetch"}, {"cmd": "run", "variants": ["baseline"]}]}) == [["fetch"], ["run", "--variant", "baseline"]]
    bad = [
        [], "run", {}, {"cmd": "rm"}, {"cmd": "request"}, {"cmd": "run"}, {"cmd": "run", "variants": []},
        {"cmd": "run", "variants": ["nope"]}, {"cmd": "run", "variants": ["baseline; rm -rf /"]},
        {"cmd": "run", "variants": ["baseline"], "out": "/tmp/x"}, {"cmd": "run", "variants": ["baseline"], "data": "x"},
        {"cmd": "run", "variants": ["baseline"], "folds": "5"}, {"cmd": "run", "variants": ["baseline"], "folds": 99},
        {"cmd": "fetch", "args": ["--out", "site/data"]}, {"cmd": "fetch", "args": ["--chips-from", "$(date)"]},
        {"cmd": "fetch", "args": ["--chips-from"]}, {"cmd": "fetch", "args": "--skip-chips"}, {"cmd": "fetch", "args": ["--synthetic"]},
        {"cmd": "compare", "base": "nope", "variant": "M1"}, {"cmd": "compare"},
        {"steps": []}, {"steps": [{"cmd": "fetch"}] * 7}, {"steps": [{"cmd": "fetch"}], "cmd": "run"},
    ]
    for req in bad:
        with pytest.raises(request.BadRequest):
            v(req)


def test_request_can_never_touch_holdout():
    for req in [
        {"cmd": "fetch", "args": ["--write-holdout"]},
        {"cmd": "run", "variants": ["baseline"], "unlock_holdout": True},
        {"cmd": "run", "variants": ["baseline"], "holdout_approved_by": "Brad"},
        {"cmd": "run", "variants": ["baseline"], "note": "please --unlock-holdout"},
        {"steps": [{"cmd": "run", "variants": ["baseline"]}], "note": "HOLDOUT ok"},
        {"cmd": "compare", "variant": "baseline", "Holdout": 1},
    ]:
        with pytest.raises(request.BadRequest, match="保留段|不允許"):
            request.validate(req)


def test_request_file_path_and_execution(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "research" / "requests").mkdir(parents=True)
    (tmp_path / "research" / "requests" / "001-run.json").write_text(json.dumps({"cmd": "run", "variants": ["baseline"]}), "utf-8")
    (tmp_path / "evil.json").write_text(json.dumps({"cmd": "run", "variants": ["baseline"]}), "utf-8")
    assert request.load_request("research/requests/001-run.json") == [["run", "--variant", "baseline"]]
    for path in ("evil.json", "research/requests/../../evil.json", "research/requests/missing.json", "research/requests/a b.json"):
        with pytest.raises(request.BadRequest):
            request.load_request(path)
    ran = []
    monkeypatch.setattr(cli, "cmd_run", lambda args: ran.append(args.variant))
    cli.main(["request", "research/requests/001-run.json"])
    assert ran == [["baseline"]]
    (tmp_path / "research" / "requests" / "002-bad.json").write_text(json.dumps({"cmd": "run", "variants": ["baseline"], "note": "holdout"}), "utf-8")
    with pytest.raises(request.BadRequest):   # 有一份不合格就全部不執行
        cli.main(["request", "research/requests/001-run.json", "research/requests/002-bad.json"])
    assert len(ran) == 1


# ---------- 命令列整段走一遍 ----------

def test_cli_synthetic_fetch_run_compare(tmp_path, monkeypatch):
    data_dir, out, trials = str(tmp_path / "data"), str(tmp_path / "results"), str(tmp_path / "trials.json")
    monkeypatch.setattr(synthetic, "universe", lambda: UNI)
    monkeypatch.setattr(runner, "universe", lambda: UNI)
    monkeypatch.setitem(runner.VARIANTS, "_probe", {"methods": {"momentum": {"max_hold": 5}}})
    monkeypatch.delenv(dataset.HOLDOUT_ENV, raising=False)
    with pytest.raises(SystemExit):
        cli.main(["fetch", "--synthetic"])   # 合成資料不能寫進 research/data
    m = cli.main(["fetch", "--synthetic", "--out", data_dir, "--days", "400", "--seed", "2"])
    assert m["synthetic"] and not (tmp_path / "data" / dataset.HOLDOUT).exists()
    res = cli.main(["run", "--variant", "baseline", "--variant", "_probe", "--data", data_dir, "--out", out, "--trials", trials])
    assert [r["variant"] for r in res] == ["baseline", "_probe"] and len(report.read_trials(trials)) == 2
    saved = json.loads((tmp_path / "results" / "baseline.json").read_text("utf-8"))
    assert saved["period"]["end"] == m["insample_end"] and saved["dates"][-1] < m["holdout_start"]
    assert "name" not in saved["methods"]["momentum"]["trades"][0]
    md = (tmp_path / "results" / "baseline.md").read_text("utf-8")
    assert "合成資料" in md and "第 5 折" in md and "保留段" not in md.split("## 市場狀態天數")[1]
    cmp = cli.main(["compare", "--variant", "_probe", "--out", out, "--trials", trials])
    assert cmp[0]["methods"]["momentum"]["affected"] and (tmp_path / "results" / "compare_baseline_vs__probe.md").exists()
    with pytest.raises(dataset.HoldoutLocked):
        cli.main(["run", "--variant", "baseline", "--data", data_dir, "--out", out, "--trials", trials, "--unlock-holdout"])
    with pytest.raises(SystemExit):
        cli.main(["run", "--variant", "nope", "--data", data_dir])
    # 經同意解鎖後：樣本內分折不變，另外多一段保留段；結果另存、不進試驗紀錄
    cli.main(["fetch", "--synthetic", "--out", data_dir, "--days", "400", "--seed", "2", "--write-holdout"])
    monkeypatch.setenv(dataset.HOLDOUT_ENV, dataset.HOLDOUT_KEY)
    full = cli.main(["run", "--variant", "baseline", "--data", data_dir, "--out", out, "--trials", trials, "--unlock-holdout"])[0]
    assert full["holdout_period"]["start"] == m["holdout_start"] and full["folds"] == saved["folds"]
    assert full["methods"]["momentum"]["equity"][:len(saved["dates"])] == saved["methods"]["momentum"]["equity"]
    assert "holdout" in full["methods"]["momentum"] and (tmp_path / "results" / "baseline.holdout.json").exists()
    assert len(report.read_trials(trials)) == 2
    assert json.loads((tmp_path / "results" / "baseline.json").read_text("utf-8"))["generated_at"] == saved["generated_at"]
