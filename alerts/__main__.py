"""python -m alerts brief [--data site/data]
python -m alerts check [--rules alerts/rules.json] [--state site/data/alerts_state.json] [--dry-run]
"""
from __future__ import annotations

import argparse
import html
import json
import logging
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import channels, hours, render, sink
from .check import evaluate, prime_news

TW = timezone(timedelta(hours=8))
HERE = Path(__file__).parent
log = logging.getLogger("alerts")


def fetch_quotes(symbols: list[str], history_fn=None) -> dict[str, dict]:
    from briefing.market import _history, compute_quote

    hist = (history_fn or _history)(symbols)
    out = {}
    for sym in symbols:
        if sym in hist:
            try:
                out[sym] = compute_quote(*hist[sym], spark_days=1)
            except ValueError as e:
                log.warning("%s 資料不足：%s", sym, e)
    return out


def fetch_news():
    from briefing import config
    from briefing.news import fetch_news as _fetch
    return _fetch(config)


def deliver(text: str, subject: str, line=channels.send_line, email=channels.send_email) -> list[str]:
    sent = []
    for name, fn in (("line", lambda: line(text)),
                     ("email", lambda: email(subject, f"<pre style='font-family:sans-serif;white-space:pre-wrap'>{html.escape(text)}</pre>"))):
        try:
            if fn():
                sent.append(name)
        except Exception as e:  # noqa: BLE001 一個通道失敗不影響另一個
            log.error("%s 推播失敗：%s", name, e)
    return sent


def cmd_brief(args) -> int:
    brief = json.loads((args.data / "latest.json").read_text("utf-8"))
    text = render.brief_text(brief)
    if args.dry_run:
        print(text)
        return 0
    # Email 早報由 python -m briefing --notify 負責，這裡只推 LINE，避免重複寄信
    deliver(text, "", email=lambda *a: False)
    return 0


def load_revenue_events(data_dir: Path) -> list[dict]:
    """早報算好的月營收變化（site/data/latest.json 的 signals.revenue_events）。"""
    try:
        brief = json.loads((data_dir / "latest.json").read_text("utf-8"))
    except (OSError, ValueError):
        return []
    return ((brief.get("signals") or {}).get("revenue_events")) or []


def run_check(rules: dict, state_path: Path, now: datetime, quotes_fn=fetch_quotes,
              news_fn=fetch_news, deliver_fn=deliver, dry_run=False,
              data_dir: Path = Path("site/data"), market_hours=False,
              record_fn=sink.record, news_every_min=30) -> list[dict]:
    state = json.loads(state_path.read_text("utf-8")) if state_path.exists() else {}
    if market_hours:
        # 盤中模式（Oracle 主機每 5 分鐘跑）：只檢查開盤中的市場；新聞與月營收每 news_every_min 分鐘看一次
        markets = hours.open_markets(now)
        rules = {**rules, "price": [r for r in rules.get("price", []) if hours.market_of(r["symbol"]) in markets]}
        last_news = state.get("news_checked_at")
        if last_news and (now - datetime.fromisoformat(last_news)).total_seconds() < news_every_min * 60 - 30:
            rules["events"], rules["revenue"] = [], {}
        if not rules["price"] and not rules.get("events") and not (rules.get("revenue") or {}).get("enabled"):
            log.info("目前沒有開盤中的市場，也還沒到看新聞的時間，略過")
            return []
    symbols = [r["symbol"] for r in rules.get("price", [])]
    quotes = quotes_fn(symbols) if symbols else {}
    news = []
    if rules.get("events"):
        try:
            news = news_fn()
        except Exception as e:  # noqa: BLE001
            log.warning("抓新聞失敗，這次只檢查價格：%s", e)
    if news and not state.get("primed"):
        state = prime_news(news, state)
        log.info("第一次執行：現有 %d 則新聞標為已讀", len(news))
    rev_events = load_revenue_events(data_dir) if (rules.get("revenue") or {}).get("enabled") else []
    alerts, new_state = evaluate(rules, quotes, news, state, now.strftime("%Y-%m-%d"), rev_events)
    new_state["primed"] = state.get("primed", False) or bool(news)
    new_state["checked_at"] = now.isoformat(timespec="minutes")
    new_state["news_checked_at"] = (now.isoformat(timespec="minutes") if rules.get("events")
                                    else state.get("news_checked_at"))

    if alerts:
        text = render.alerts_text(alerts)
        if dry_run:
            print(text)
        else:
            sent = deliver_fn(text, f"投資警報｜{alerts[0]['text'][:60]}")
            record_fn(alerts, now.isoformat(timespec="seconds"), state_path.parent / "alerts_history.json")
            if not sent:
                log.warning("有 %d 則警報但沒有任何通道送出（檢查 LINE/Email 設定）", len(alerts))
    else:
        log.info("沒有觸發任何警報")
    if not dry_run:
        state_path.parent.mkdir(parents=True, exist_ok=True)
        state_path.write_text(json.dumps(new_state, ensure_ascii=False, indent=1), "utf-8")
    return alerts


def cmd_check(args) -> int:
    rules = json.loads(args.rules.read_text("utf-8"))
    run_check(rules, args.state, datetime.now(TW), dry_run=args.dry_run, data_dir=args.data,
              market_hours=args.market_hours)
    return 0


def main(argv=None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(prog="python -m alerts")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("brief", help="把最新早報推到 LINE")
    b.add_argument("--data", default="site/data", type=Path)
    b.add_argument("--dry-run", action="store_true", help="只印出，不推送")
    c = sub.add_parser("check", help="檢查價格／事件警報")
    c.add_argument("--rules", default=HERE / "rules.json", type=Path)
    c.add_argument("--state", default=Path("site/data/alerts_state.json"), type=Path)
    c.add_argument("--dry-run", action="store_true", help="只印出，不推送也不存狀態")
    c.add_argument("--data", default=Path("site/data"), type=Path, help="早報資料夾（讀月營收變化）")
    c.add_argument("--market-hours", action="store_true",
                   help="盤中模式：只檢查開盤中的市場（給每幾分鐘跑一次的排程用）")
    sub.add_parser("test", help="寄一封測試信／推一則測試訊息，確認通道設定正確")
    args = ap.parse_args(argv)
    if args.cmd == "test":
        sent = deliver(f"✅ 投資警報測試訊息（{datetime.now(TW):%Y-%m-%d %H:%M}）", "投資警報｜測試")
        print("已送出：" + (", ".join(sent) if sent else "沒有任何通道（檢查設定）"))
        return 0 if sent else 1
    return cmd_brief(args) if args.cmd == "brief" else cmd_check(args)


if __name__ == "__main__":
    sys.exit(main())
