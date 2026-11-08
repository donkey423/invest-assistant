"""產生持股分析。

  python -m holdings                 讀 private/holdings.csv，寫 site/data/private/holdings.json（自己電腦用）
  python -m holdings --supabase      讀 Supabase 的持股（手機新增的），算好寫回 Supabase（排程用）
  加 --no-ai 只算數字，不呼叫 Claude。

步驟：讀持股 → 抓行情與匯率 → 程式算數字 →（可選）Claude 寫健檢。
AI 失敗時保留上一份的文字分析，數字照樣更新。
"""
from __future__ import annotations

import argparse
import json
import logging
import os
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import config
from .analyze import analyze
from .health import health
from .calc import allocation, realized_pnl, risk, totals, value_positions
from .model import Position, Transaction, load_positions, load_transactions

TW = timezone(timedelta(hours=8))
log = logging.getLogger("holdings")


def _default_history(symbols):
    from briefing.market import _history  # 和早報共用同一個行情來源
    return _history(symbols)


def _symbols(positions: list[Position], cfg) -> list[str]:
    syms = [p.quote_symbol for p in positions]
    syms += list(cfg.FX_SYMBOLS.values()) + [b["symbol"] for b in cfg.BENCHMARKS]
    syms += [s["symbol"] for s in cfg.SCENARIOS if "symbol" in s]
    return list(dict.fromkeys(syms))


def compute_report(positions: list[Position], txs: list[Transaction], hist: dict, cfg=config, *,
                   previous: dict | None = None, briefing: dict | None = None,
                   analyze_fn=analyze, use_ai: bool = True, now: datetime | None = None) -> dict:
    """純計算：不讀寫檔案，檔案模式和 Supabase 模式共用。"""
    now = now or datetime.now(TW)
    if not positions:
        raise RuntimeError("沒有任何持股")
    rows, warnings = value_positions(positions, hist, cfg, now.date())
    if all("error" in r for r in rows):
        raise RuntimeError("所有持股都抓不到行情，保留上一份分析")
    realized = realized_pnl(txs, hist, cfg, now.date())
    report = {
        "generated_at": now.isoformat(timespec="minutes"),
        "base_currency": cfg.BASE_CURRENCY,
        "totals": totals(rows, realized),
        "positions": rows,
        "allocation": allocation(rows, cfg),
        "risk": risk(rows, hist, cfg),
        "realized": realized,
        "warnings": warnings,
        "analysis": (previous or {}).get("analysis"),
    }
    try:
        report["health"] = health(rows, report["allocation"], report["risk"], briefing, cfg)
    except Exception as e:  # noqa: BLE001 健檢失敗不影響其他數字
        log.error("持股健檢失敗：%s", e)
    if use_ai:
        try:
            report["analysis"] = analyze_fn(report, briefing)
            report["analysis"]["generated_at"] = report["generated_at"]
        except Exception as e:  # noqa: BLE001
            log.error("AI 分析失敗：%s", e)
            prev_at = (report["analysis"] or {}).get("generated_at")
            warnings.append(f"AI 分析這次失敗，顯示的是上一份（{prev_at}）" if prev_at else "AI 分析這次失敗")
    return report


def _read_json(p: Path) -> dict | None:
    return json.loads(p.read_text("utf-8")) if p.exists() else None


def build(holdings_csv: Path, out_dir: Path, cfg=config, history_fn=_default_history,
          analyze_fn=analyze, tx_csv: Path | None = None, briefing_json: Path | None = None,
          use_ai: bool = True, now: datetime | None = None) -> dict:
    """檔案模式：讀 CSV，寫 holdings.json。"""
    positions = load_positions(holdings_csv)
    if not positions:
        raise RuntimeError(f"{holdings_csv} 沒有任何持股")
    txs = load_transactions(tx_csv or cfg.TRANSACTIONS_CSV)
    out_dir.mkdir(parents=True, exist_ok=True)
    latest = out_dir / "holdings.json"
    report = compute_report(positions, txs, history_fn(_symbols(positions, cfg)), cfg,
                            previous=_read_json(latest),
                            briefing=_read_json(briefing_json or cfg.BRIEFING_JSON),
                            analyze_fn=analyze_fn, use_ai=use_ai, now=now)
    latest.write_text(json.dumps(report, ensure_ascii=False, indent=1), "utf-8")
    log.info("已寫入 %s（%d 檔，總市值 %s 元）", latest, report["totals"]["positions"], f"{report['totals']['value_twd']:,}")
    return report


def build_store(store, cfg=config, history_fn=_default_history, analyze_fn=analyze,
                briefing_json: Path | None = None, use_ai: bool = True, now: datetime | None = None) -> dict:
    """資料庫模式：每個使用者各算一份，寫回資料庫。回傳 {user_id: report 或錯誤訊息}。"""
    users = store.load()
    if not users:
        log.info("資料庫裡還沒有任何持股")
        return {}
    all_pos = [p for u in users.values() for p in u["positions"]]
    hist = history_fn(_symbols(all_pos, cfg))  # 所有人的代號一次抓完
    briefing = _read_json(briefing_json or cfg.BRIEFING_JSON)  # 健檢要用產業鏈訊號
    results = {}
    for uid, u in users.items():
        try:
            report = compute_report(u["positions"], u["transactions"], hist, cfg, previous=store.previous(uid),
                                    briefing=briefing, analyze_fn=analyze_fn, use_ai=use_ai, now=now)
            report["warnings"] = u["warnings"] + report["warnings"]
            store.save(uid, report)
            results[uid] = report
            log.info("使用者 %s…：%d 檔，總市值 %s 元", uid[:8], report["totals"]["positions"], f"{report['totals']['value_twd']:,}")
        except Exception as e:  # noqa: BLE001 一個人失敗不影響其他人
            log.error("使用者 %s… 計算失敗：%s", uid[:8], e)
            results[uid] = str(e)
    return results


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=config.HOLDINGS_CSV, type=Path)
    ap.add_argument("--transactions", default=config.TRANSACTIONS_CSV, type=Path)
    ap.add_argument("--out", default=config.OUT_DIR, type=Path)
    ap.add_argument("--supabase", action="store_true", help="從 Supabase 讀持股、把結果寫回 Supabase")
    ap.add_argument("--no-ai", action="store_true", help="只算數字，不呼叫 Claude")
    args = ap.parse_args()
    # 沒設 API key 就自動不跑 AI，不會失敗
    use_ai = not args.no_ai and bool(os.environ.get("ANTHROPIC_API_KEY"))
    if not use_ai and not args.no_ai:
        log.info("沒有 ANTHROPIC_API_KEY，這次只算數字")
    if args.supabase:
        from .store import store_from_env
        results = build_store(store_from_env(config.SUPABASE_URL), use_ai=use_ai)
        if results and all(isinstance(r, str) for r in results.values()):
            raise SystemExit("所有使用者都計算失敗")
    else:
        build(args.csv, args.out, tx_csv=args.transactions, use_ai=use_ai)


if __name__ == "__main__":
    main()
