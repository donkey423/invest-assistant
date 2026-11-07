"""產生持股分析：python -m holdings [--no-ai] [--csv private/holdings.csv]

步驟：讀持股 → 抓行情與匯率 → 程式算數字 → Claude 寫健檢 → 寫成 site/data/private/holdings.json。
AI 失敗時保留上一份的文字分析，數字照樣更新。
"""
from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import config
from .analyze import analyze
from .calc import allocation, realized_pnl, risk, totals, value_positions
from .model import load_positions, load_transactions

TW = timezone(timedelta(hours=8))
log = logging.getLogger("holdings")


def _default_history(symbols):
    from briefing.market import _history  # 和早報共用同一個行情來源
    return _history(symbols)


def build(holdings_csv: Path, out_dir: Path, cfg=config, history_fn=_default_history,
          analyze_fn=analyze, tx_csv: Path | None = None, briefing_json: Path | None = None,
          use_ai: bool = True, now: datetime | None = None) -> dict:
    now = now or datetime.now(TW)
    positions = load_positions(holdings_csv)
    if not positions:
        raise RuntimeError(f"{holdings_csv} 沒有任何持股")
    txs = load_transactions(tx_csv or cfg.TRANSACTIONS_CSV)

    syms = [p.quote_symbol for p in positions]
    syms += list(cfg.FX_SYMBOLS.values()) + [b["symbol"] for b in cfg.BENCHMARKS]
    syms += [s["symbol"] for s in cfg.SCENARIOS if "symbol" in s]
    hist = history_fn(list(dict.fromkeys(syms)))

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
    }

    out_dir.mkdir(parents=True, exist_ok=True)
    latest = out_dir / "holdings.json"
    previous = json.loads(latest.read_text("utf-8")) if latest.exists() else {}
    report["analysis"] = previous.get("analysis")
    if use_ai:
        bj = briefing_json or cfg.BRIEFING_JSON
        briefing = json.loads(bj.read_text("utf-8")) if bj.exists() else None
        try:
            report["analysis"] = analyze_fn(report, briefing)
            report["analysis"]["generated_at"] = report["generated_at"]
        except Exception as e:  # noqa: BLE001
            log.error("AI 分析失敗：%s", e)
            if report["analysis"]:
                warnings.append(f"AI 分析這次失敗，顯示的是上一份（{report['analysis'].get('generated_at', '無')}）")
            else:
                warnings.append("AI 分析這次失敗")

    latest.write_text(json.dumps(report, ensure_ascii=False, indent=1), "utf-8")
    log.info("已寫入 %s（%d 檔，總市值 %s 元）", latest, report["totals"]["positions"], f"{report['totals']['value_twd']:,}")
    return report


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", default=config.HOLDINGS_CSV, type=Path)
    ap.add_argument("--transactions", default=config.TRANSACTIONS_CSV, type=Path)
    ap.add_argument("--out", default=config.OUT_DIR, type=Path)
    ap.add_argument("--no-ai", action="store_true", help="只算數字，不呼叫 Claude")
    args = ap.parse_args()
    build(args.csv, args.out, tx_csv=args.transactions, use_ai=not args.no_ai)


if __name__ == "__main__":
    main()
