"""把觸發的警報記在狀態檔旁的 alerts_history.json（最近 200 筆），方便在主機上回查。"""
from __future__ import annotations

import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)
KEEP_LOCAL = 200


def to_rows(alerts: list[dict], now_iso: str) -> list[dict]:
    return [{"created_at": now_iso, "kind": a["kind"], "alert_key": a["key"],
             "text": a["text"], "url": a.get("url")} for a in alerts]


def save_local(rows: list[dict], path: Path) -> None:
    old = json.loads(path.read_text("utf-8")) if path.exists() else []
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps((rows[::-1] + old)[:KEEP_LOCAL], ensure_ascii=False, indent=1), "utf-8")


def record(alerts: list[dict], now_iso: str, local_path: Path) -> None:
    try:
        save_local(to_rows(alerts, now_iso), local_path)
    except Exception as e:  # noqa: BLE001 紀錄失敗不影響 Email
        log.error("警報紀錄寫入失敗：%s", e)
