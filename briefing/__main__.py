"""產生一份早報：python -m briefing [--notify] [--out site/data]

步驟：抓行情 → 抓新聞 → Claude 摘要 → 寫成 latest.json（並另存一份到 archive/）。
任何一步失敗都盡量保留上一份的內容，不讓網頁整個壞掉。
"""
from __future__ import annotations

import argparse
import json
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path

from . import config
from .chips import build_chips
from .market import build_market
from .news import fetch_news
from .notify import send_email
from .summarize import FREE_MODEL, summarize
from .ai_file import NEWS_FILE, load_fresh
from .signals import build_signals
from .world import build_world

TW = timezone(timedelta(hours=8))
log = logging.getLogger("briefing")


def build(out_dir: Path, market_fn=build_market, news_fn=fetch_news, summary_fn=summarize,
          chips_fn=build_chips) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    latest = out_dir / "latest.json"
    previous = json.loads(latest.read_text("utf-8")) if latest.exists() else {}

    market = market_fn(config)
    if "error" in market["taiex"] and all("error" in q for q in market["global"]):
        raise RuntimeError("所有行情都抓不到，保留上一份早報")

    prev_chips = (previous.get("market") or {}).get("chips")
    # 台股籌碼（證交所）：抓不到就沿用上一份，不影響其他區塊
    try:
        chips = chips_fn(config, prev_chips)
    except Exception as e:  # noqa: BLE001
        log.error("台股籌碼抓取失敗：%s", e)
        chips = None
    market["chips"] = chips or prev_chips

    # 產業鏈訊號：抓不到就沿用上一份
    try:
        signals = build_signals(config, market, previous.get("signals"), out_dir)
    except Exception as e:  # noqa: BLE001
        log.error("產業鏈訊號失敗：%s", e)
        signals = previous.get("signals")

    news = news_fn(config)
    warnings = []
    try:
        summary = summary_fn(market, news) if news else None
        if summary is None:
            raise RuntimeError("沒有抓到任何新聞")
    except Exception as e:  # noqa: BLE001
        log.error("AI 摘要失敗：%s", e)
        summary = previous.get("summary")
        warnings.append(f"AI 摘要這次失敗，顯示的是上一份（{previous.get('generated_at', '無')}）")

    # 沒有 API key 時，改用雲端排程以你的 Claude 帳號寫好的摘要（夠新才用）
    if summary is None or summary.get("model") == FREE_MODEL:
        account_summary = load_fresh(out_dir)
        if account_summary:
            summary = account_summary

    now = datetime.now(TW)
    # 給雲端排程寫 AI 摘要用的新聞清單
    (out_dir / NEWS_FILE).write_text(json.dumps(news, ensure_ascii=False, indent=1), "utf-8")
    brief = {
        "generated_at": now.isoformat(timespec="minutes"),
        "market": market,
        "summary": summary,
        "world": build_world(config, news, summary),
        "signals": signals,
        "news_count": len(news),
        "warnings": warnings,
    }
    text = json.dumps(brief, ensure_ascii=False, indent=1)
    latest.write_text(text, "utf-8")
    archive = out_dir / "archive"
    archive.mkdir(exist_ok=True)
    (archive / f"{now:%Y-%m-%d_%H%M}.json").write_text(text, "utf-8")
    log.info("已寫入 %s（新聞 %d 則）", latest, len(news))
    return brief


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="site/data", type=Path)
    ap.add_argument("--notify", action="store_true", help="產生後寄 Email 並推 LINE")
    args = ap.parse_args()
    brief = build(args.out)
    if args.notify:
        try:  # Email 失敗不影響 LINE
            send_email(brief)
        except Exception as e:  # noqa: BLE001
            log.error("Email 寄送失敗：%s", e)
        try:  # LINE 失敗不影響早報 JSON 與 Email
            from alerts.channels import send_line
            from alerts.render import brief_text
            send_line(brief_text(brief))
        except Exception as e:  # noqa: BLE001
            log.error("LINE 推播失敗：%s", e)


if __name__ == "__main__":
    main()
