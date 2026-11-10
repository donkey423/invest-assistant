"""從 site/data/archive/ 的歷史早報重建訊號回測紀錄：python tools/rebuild_signal_log.py

用在紀錄被錯誤資料蓋掉的時候（例如 2026-11-10 指數資料落後，把 11/9 的價格記到 11/6）。
依時間順序重放每一份存檔，套用和每天排程相同的規則。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from briefing import backtest  # noqa: E402


def main(data_dir: Path) -> None:
    entries: list[dict] = []
    for f in sorted((data_dir / "archive").glob("*.json")):
        brief = json.loads(f.read_text("utf-8"))
        signals = brief.get("signals") or {}
        date = backtest.trade_date(signals)
        if not date:
            continue
        # 舊存檔沒有對照指數的資料日，從行情區塊補
        m = brief.get("market") or {}
        as_of = {q.get("symbol"): q.get("as_of") for q in [m.get("taiex") or {}, *(m.get("gauges") or [])]}
        for c in signals.get("chains") or []:
            p = c.get("price") or {}
            p.setdefault("bench_as_of", as_of.get(p.get("bench")))
        entries = backtest.update_log(entries, date, signals)
    (data_dir / backtest.LOG_FILE).write_text(json.dumps(entries, ensure_ascii=False, separators=(",", ":")), "utf-8")
    for e in entries:
        n = sum(len(c["prices"]) for c in e["chains"].values())
        print(e["date"], "鏈", len(e["chains"]), "價格", n)


if __name__ == "__main__":
    main(Path(sys.argv[1] if len(sys.argv) > 1 else "site/data"))
