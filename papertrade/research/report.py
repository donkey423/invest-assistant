"""研究結果的輸出：試驗紀錄（trials.json）、變體對 baseline 的比較、Markdown 表格。"""
from __future__ import annotations

import json
from pathlib import Path
from statistics import variance

from .. import config as C
from .. import metrics

REGISTERED_TRIALS = 12   # HYPOTHESES.md 第 5 節事先登記的試驗次數；Deflated Sharpe 至少以這個數計
DIFF_KEYS = ("sharpe", "cagr", "max_drawdown", "calmar", "turnover")
SLIM_TRADE = ("date", "side", "code", "shares", "price", "fee", "pnl", "pnl_pct", "reason", "held_from", "partial")


# ---------- 試驗紀錄 ----------

def read_trials(path) -> list[dict]:
    try:
        rows = json.loads(Path(path).read_text("utf-8"))
        return rows if isinstance(rows, list) else []
    except (OSError, ValueError):
        return []


def log_trial(path, res: dict) -> dict:
    """把這次執行追加到試驗紀錄。每次 run 都記，不管結果好壞。"""
    entry = {"variant": res["variant"], "hash": res["hash"], "code": res["code"], "at": res["generated_at"],
             "dataset": res["dataset"], "synthetic": res.get("synthetic", False),
             "sharpe": {mid: {"all": m["all"]["sr_period"], "folds": [f["sr_period"] for f in m["folds"]]}
                        for mid, m in res["methods"].items()}}
    rows = [*read_trials(path), entry]
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(rows, ensure_ascii=False, indent=1), "utf-8")
    return entry


def n_trials(trials: list[dict]) -> int:
    """Deflated Sharpe 用的試驗次數：紀錄中不同旗標內容（hash）的個數，至少 REGISTERED_TRIALS。

    同一組旗標重跑不會多算；改了旗標內容就算新的一次。baseline 也算一筆（偏保守）。
    """
    return max(len({t["hash"] for t in trials}), REGISTERED_TRIALS)


def var_trials(trials: list[dict], method: str, dataset: str | None = None) -> float | None:
    """某方法在各試驗（每個 hash 取最新一筆、同一份資料集）的「每期夏普」變異數；不足 2 筆回傳 None。"""
    latest = {}
    for t in trials:
        if dataset and t.get("dataset") != dataset:
            continue
        sr = ((t.get("sharpe") or {}).get(method) or {}).get("all")
        if sr is not None:
            latest[t["hash"]] = sr
    return variance(latest.values()) if len(latest) >= 2 else None


# ---------- 比較 ----------

def _returns(m: dict) -> list[float]:
    return metrics.daily_returns([C.START_CASH, *m["equity"]])


def _diff(v: dict, b: dict) -> dict:
    return {k: (v[k] - b[k] if v.get(k) is not None and b.get(k) is not None else None) for k in DIFF_KEYS}


def _wins(vf: list[dict], bf: list[dict], key: str) -> int:
    return sum(1 for v, b in zip(vf, bf) if v.get(key) is not None and b.get(key) is not None and v[key] > b[key])


def _held(m: dict, dates: list[str]) -> list[frozenset]:
    """由交易紀錄還原每個評估日收盤時的持股。"""
    by_day = {}
    for t in m["trades"]:
        by_day.setdefault(t["date"], []).append(t)
    cur, out = set(), []
    for d in dates:
        for t in by_day.get(d, []):
            if t.get("partial"):   # 部分減碼／加碼（假設 E1）不改變持有哪些股票
                continue
            (cur.add if t["side"] == "買" else cur.discard)(t["code"])
        out.append(frozenset(cur))
    return out


def overlap(v: dict, b: dict, dates: list[str]) -> float | None:
    """持股重疊率：每天「兩邊都持有的檔數 ÷ 兩邊持股檔數較多者」的平均（兩邊都空手的日子不計）。"""
    xs = [len(x & y) / max(len(x), len(y)) for x, y in zip(_held(v, dates), _held(b, dates)) if x or y]
    return sum(xs) / len(xs) if xs else None


def compare(base: dict, var: dict, trials: list[dict], block: int = 21, n_boot: int = 2000) -> dict:
    """變體對 baseline：逐方法、逐折與全期的差異，夏普差的成對區塊拔靴信賴區間，變體的 Deflated Sharpe。"""
    if base["dataset"] != var["dataset"]:
        raise ValueError(f"兩份結果用的資料集不同（{base['dataset']} / {var['dataset']}），不能比較，請重跑 baseline")
    if base["dates"] != var["dates"]:
        raise ValueError("兩份結果的評估日不同，不能比較")
    n = n_trials(trials)
    out = {"base": base["variant"], "variant": var["variant"], "flags": var["flags"], "hash": var["hash"],
           "dataset": var["dataset"], "n_trials": n, "period": var["period"], "folds": var["folds"],
           "regime": var["regime"], "methods": {}}
    for mid, v in var["methods"].items():
        b = base["methods"].get(mid)
        if not b:
            continue
        hold = ({"holdout": {"base": {k: b["holdout"][k] for k in DIFF_KEYS}, "variant": {k: v["holdout"][k] for k in DIFF_KEYS},
                             "diff": _diff(v["holdout"], b["holdout"])}} if "holdout" in v and "holdout" in b else {})
        rv, rb = _returns(v), _returns(b)
        vt = var_trials(trials, mid, var["dataset"])
        dsr = metrics.deflated_sharpe(rv, n, vt if vt is not None else 0.0)
        extra = lambda x: {k: x["all"][k] for k in ("avg_positions", "avg_exposure", "stop_exits", "fees", "n_trades", "dividends")}  # noqa: E731
        out["methods"][mid] = {
            "name": v["name"], "affected": v["equity"] != b["equity"] or len(v["trades"]) != len(b["trades"]),
            "all": {"base": {k: b["all"][k] for k in DIFF_KEYS}, "variant": {k: v["all"][k] for k in DIFF_KEYS},
                    "diff": _diff(v["all"], b["all"])},
            "folds": [_diff(x, y) for x, y in zip(v["folds"], b["folds"])],
            "wins": {"sharpe": _wins(v["folds"], b["folds"], "sharpe"), "calmar": _wins(v["folds"], b["folds"], "calmar"),
                     "of": len(v["folds"])},
            "sharpe_diff_ci": metrics.block_bootstrap_diff(rv, rb, block=block, n_boot=n_boot),
            "dsr": dsr, "var_trials": vt,
            "dsr_note": "" if vt is not None else "試驗紀錄不足 2 筆，算不出各試驗夏普的變異數；此處的 DSR 等同「對 0 的 PSR」，沒有扣掉多重試驗",
            "extra": {"base": extra(b), "variant": extra(v)}, "overlap": overlap(v, b, var["dates"]), **hold,
        }
    return out


# ---------- 輸出 ----------

def _pct(x, digits=1, sign=False) -> str:
    return "—" if x is None else f"{x * 100:{'+' if sign else ''}.{digits}f}%"


def _num(x, digits=2, sign=False) -> str:
    return "—" if x is None else f"{x:{'+' if sign else ''}.{digits}f}"


def _row(label: str, m: dict) -> str:
    return (f"| {label} | {m['days'] - 1} | {_pct(m['total_return'])} | {_pct(m['cagr'])} | {_pct(m['vol'])} | {_num(m['sharpe'])} | "
            f"{_pct(m['max_drawdown'])} | {_num(m['calmar'])} | {_num(m['turnover'], 1)} | {m['n_trades']} | "
            f"{_num(m.get('avg_positions'), 1)} | {_pct(m.get('avg_exposure'), 0)} | {m.get('stop_exits', '—')} |")


HEAD = ("| 期間 | 天數 | 總報酬 | 年化報酬 | 年化波動 | 夏普 | 最大回撤 | Calmar | 年換手（倍） | 交易筆數 | 平均持股檔數 | 平均持股比例 | 停損次數 |\n"
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|")
CAVEAT = ("> 選股池是事後挑的產業鏈代表股，所有絕對數字都偏好看；只有「變體對 baseline」的差有意義。"
          "沒有漲跌停、成交量、滑價模型；零股以開盤價成交。景氣燈號寫死紅燈（未驗證參數）。")


def result_markdown(res: dict) -> str:
    p = res["period"]
    lines = [f"# 研究結果：{res['variant']}", "",
             f"- 樣本內期間：{p['start']}～{p['end']}（{p['days']} 個交易日），分 {len(res['folds'])} 折",
             f"- 旗標：`{json.dumps(res['flags'], ensure_ascii=False)}`（hash {res['hash']}，程式 {res['code']}，資料集 {res['dataset']}）",
             f"- 產生時間：{res['generated_at']}" + ("；**合成資料，數字沒有任何意義**" if res.get("synthetic") else ""),
             "- 已套用的修正：VIX 延後一天、現金股利除息日入帳、期末持股扣賣出成本。", "", CAVEAT, ""]
    g = res["regime"]
    lines += ["## 市場狀態天數", "", "| 期間 | 大盤低於季線 | 大盤低於年線 | VIX ≥ 25 |", "|---|---|---|---|",
              f"| 全期 | {g['all']['below_ma60']} | {g['all']['below_ma200']} | {g['all']['vix25']} |"]
    lines += [f"| 第 {i + 1} 折（{f['start']}～{f['end']}） | {x['below_ma60']} | {x['below_ma200']} | {x['vix25']} |"
              for i, (f, x) in enumerate(zip(res["folds"], g["folds"]))]
    blank = {"avg_positions": None, "avg_exposure": None, "stop_exits": "—"}
    for key, m in [*res["benchmarks"].items(), *res["methods"].items()]:
        lines += ["", f"## {m['name']}（{key}）", "", HEAD, _row("全期", {**blank, **m["all"]})]
        lines += [_row(f"第 {i + 1} 折", {**blank, **f}) for i, f in enumerate(m["folds"])]
        if "holdout" in m:
            lines.append(_row("**保留段**", {**blank, **m["holdout"]}))
        if "equity" in m:
            lines.append(f"\n期末持股賣出成本 {m['all']['exit_cost']:,} 元已從最後一天淨值扣除；期間現金股利入帳 {m['all']['dividends']:,} 元。")
    return "\n".join(lines) + "\n"


def compare_markdown(cmp: dict) -> str:
    lines = [f"# 比較：{cmp['variant']} 對 {cmp['base']}", "",
             f"- 期間：{cmp['period']['start']}～{cmp['period']['end']}（{cmp['period']['days']} 個交易日，{len(cmp['folds'])} 折）",
             f"- 旗標：`{json.dumps(cmp['flags'], ensure_ascii=False)}`；Deflated Sharpe 的試驗次數 N = {cmp['n_trials']}"
             f"（試驗紀錄的不同旗標數，至少 {REGISTERED_TRIALS}）",
             "- 「差」＝變體減 baseline；百分比欄位的差是百分點。", "", CAVEAT, ""]
    same = [m["name"] for m in cmp["methods"].values() if not m["affected"]]
    if same:
        lines += [f"沒有受影響（淨值與交易完全相同）的方法：{'、'.join(same)}。", ""]
    for mid, m in cmp["methods"].items():
        if not m["affected"]:
            continue
        a, ci, d = m["all"], m["sharpe_diff_ci"], m["dsr"] or {}
        lines += [f"## {m['name']}（{mid}）", "", "| | 夏普 | 年化報酬 | 最大回撤 | Calmar | 年換手（倍） |", "|---|---|---|---|---|---|",
                  f"| baseline | {_num(a['base']['sharpe'])} | {_pct(a['base']['cagr'])} | {_pct(a['base']['max_drawdown'])} | {_num(a['base']['calmar'])} | {_num(a['base']['turnover'], 1)} |",
                  f"| 變體 | {_num(a['variant']['sharpe'])} | {_pct(a['variant']['cagr'])} | {_pct(a['variant']['max_drawdown'])} | {_num(a['variant']['calmar'])} | {_num(a['variant']['turnover'], 1)} |",
                  f"| 差（全期） | {_num(a['diff']['sharpe'], sign=True)} | {_pct(a['diff']['cagr'], sign=True)} | {_pct(a['diff']['max_drawdown'], sign=True)} | {_num(a['diff']['calmar'], sign=True)} | {_num(a['diff']['turnover'], 1, sign=True)} |"]
        lines += [f"| 差（第 {i + 1} 折） | {_num(f['sharpe'], sign=True)} | {_pct(f['cagr'], sign=True)} | {_pct(f['max_drawdown'], sign=True)} | {_num(f['calmar'], sign=True)} | {_num(f['turnover'], 1, sign=True)} |"
                  for i, f in enumerate(m["folds"])]
        if "holdout" in m:
            h = m["holdout"]["diff"]
            lines.append(f"| **差（保留段）** | {_num(h['sharpe'], sign=True)} | {_pct(h['cagr'], sign=True)} | {_pct(h['max_drawdown'], sign=True)} | {_num(h['calmar'], sign=True)} | {_num(h['turnover'], 1, sign=True)} |")
        w, eb, ev = m["wins"], m["extra"]["base"], m["extra"]["variant"]
        lines += ["", f"- 變體勝出的折數：夏普 {w['sharpe']}/{w['of']}、Calmar {w['calmar']}/{w['of']}",
                  f"- 夏普差的 95% 信賴區間（成對區塊拔靴）：{_num(ci['ci_low'], sign=True)}～{_num(ci['ci_high'], sign=True)}，差大於 0 的比例 {_pct(ci['p_gt0'], 0)}",
                  f"- 變體的 Deflated Sharpe：{_num(d.get('dsr'), 3)}（年化夏普 {_num(d.get('sr_annual'))}，門檻每期 {_num(d.get('sr0'), 4)}）"
                  + (f"。注意：{m['dsr_note']}" if m["dsr_note"] else ""),
                  f"- 平均持股檔數 {_num(eb['avg_positions'], 1)} → {_num(ev['avg_positions'], 1)}；平均持股比例 {_pct(eb['avg_exposure'], 0)} → {_pct(ev['avg_exposure'], 0)}；"
                  f"停損次數 {eb['stop_exits']} → {ev['stop_exits']}；費用 {eb['fees']:,.0f} → {ev['fees']:,.0f} 元；持股重疊率 {_pct(m['overlap'], 0)}", ""]
    g = cmp["regime"]["all"]
    lines += [f"市場狀態（全期天數）：大盤低於季線 {g['below_ma60']}、低於年線 {g['below_ma200']}、VIX ≥ 25 {g['vix25']}。"]
    return "\n".join(lines) + "\n"


def write_result(out_dir, res: dict) -> Path:
    """寫 <變體>.json 與 <變體>.md；解鎖保留段的結果另存 <變體>.holdout.*，不蓋掉樣本內結果。"""
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    stem = res["variant"] + (".holdout" if res.get("holdout_unlocked") else "")
    slim = copy_slim(res)
    (out / f"{stem}.json").write_text(json.dumps(slim, ensure_ascii=False, separators=(",", ":")), "utf-8")
    (out / f"{stem}.md").write_text(result_markdown(res), "utf-8")
    return out / f"{stem}.json"


def copy_slim(res: dict) -> dict:
    """存檔用：交易紀錄只留必要欄位（名稱可由代號查回）。"""
    methods = {mid: {**m, "trades": [{k: t[k] for k in SLIM_TRADE if k in t} for t in m["trades"]]}
               for mid, m in res["methods"].items()}
    return {**res, "methods": methods}


def write_compare(out_dir, cmp: dict) -> Path:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    stem = f"compare_{cmp['base']}_vs_{cmp['variant']}"
    (out / f"{stem}.json").write_text(json.dumps(cmp, ensure_ascii=False, indent=1), "utf-8")
    (out / f"{stem}.md").write_text(compare_markdown(cmp), "utf-8")
    return out / f"{stem}.md"
