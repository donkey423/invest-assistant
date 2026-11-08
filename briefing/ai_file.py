"""用你的 Claude 帳號寫的 AI 摘要（不需要 API key）。

雲端排程每個交易日早上讀 site/data/latest.json 與 news.json，
寫出 site/data/ai_summary.json 並推回 GitHub。之後的早報產生時，
若沒有 API key、而這份檔案夠新，就用它取代免費模式的摘要。

檢查檔案格式：python -m briefing.ai_file check [site/data]
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .summarize import TAGS

TW = timezone(timedelta(hours=8))
FILE_NAME = "ai_summary.json"
NEWS_FILE = "news.json"
MAX_AGE = timedelta(hours=10)  # 早上寫的摘要用到傍晚，晚上那次回到免費模式


def validate(data: dict, news_urls: set[str] | None = None) -> list[str]:
    """回傳問題清單；空清單代表格式正確。"""
    problems = []
    for key in ("written_at", "headline", "market_comment", "points"):
        if not data.get(key):
            problems.append(f"缺少 {key}")
    try:
        datetime.fromisoformat(data.get("written_at", ""))
    except ValueError:
        problems.append("written_at 不是 ISO 時間，例如 2026-11-09T07:50+08:00")
    for key in ("world_headline", "ai_headline"):  # 選填
        if key in data and not (isinstance(data[key], str) and data[key].strip()):
            problems.append(f"{key} 若有填，要是一句話")
    points = data.get("points") or []
    if not 3 <= len(points) <= 6:
        problems.append(f"points 要 3 到 6 則，現在是 {len(points)} 則")
    for i, p in enumerate(points):
        if p.get("tag") not in TAGS:
            problems.append(f"第 {i + 1} 則的 tag 要是 {TAGS} 之一")
        for k in ("title", "summary"):
            if not p.get(k):
                problems.append(f"第 {i + 1} 則缺少 {k}")
        srcs = p.get("sources") or []
        if not srcs:
            problems.append(f"第 {i + 1} 則沒有附來源")
        for s in srcs:
            if not s.get("url") or not s.get("title"):
                problems.append(f"第 {i + 1} 則的來源缺 title 或 url")
            elif news_urls is not None and s["url"] not in news_urls:
                problems.append(f"第 {i + 1} 則的來源不在 news.json 裡：{s['url']}")
    problems += _validate_themes(data.get("themes"), news_urls)
    return problems


THEME_KEYS = ("title", "chain", "reasoning", "counter", "priced_in")


def _validate_themes(themes, news_urls: set[str] | None) -> list[str]:
    """主題推理（選填）：今天的訊號 → 哪條產業鏈 → 觀察標的，一定要附反方理由與「是否已反映」。"""
    if themes is None:
        return []
    if not isinstance(themes, list) or len(themes) > 3:
        return ["themes 若有填，要是 1 到 3 則的清單"]
    problems = []
    for i, t in enumerate(themes):
        for k in THEME_KEYS:
            if not (isinstance(t.get(k), str) and t[k].strip()):
                problems.append(f"主題第 {i + 1} 則缺少 {k}")
        watch = t.get("watch")
        if not (isinstance(watch, list) and watch and all(isinstance(w, str) for w in watch)):
            problems.append(f"主題第 {i + 1} 則的 watch 要列出觀察標的")
        for src in t.get("sources") or []:
            if not src.get("url") or not src.get("title"):
                problems.append(f"主題第 {i + 1} 則的來源缺 title 或 url")
            elif news_urls is not None and src["url"] not in news_urls:
                problems.append(f"主題第 {i + 1} 則的來源不在 news.json 裡：{src['url']}")
    return problems


def load_fresh(out_dir: Path, now: datetime | None = None) -> dict | None:
    """檔案存在、格式正確、且在 MAX_AGE 內寫的，才回傳可直接當 summary 用的內容。"""
    path = out_dir / FILE_NAME
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text("utf-8"))
    except ValueError:
        return None
    if validate(data):
        return None
    written = datetime.fromisoformat(data["written_at"])
    if written.tzinfo is None:
        written = written.replace(tzinfo=TW)
    now = now or datetime.now(TW)
    if not timedelta(0) <= now - written <= MAX_AGE:
        return None
    return {
        **{k: data[k] for k in ("world_headline", "ai_headline", "themes") if data.get(k)},
        "headline": data["headline"],
        "market_comment": data["market_comment"],
        "points": data["points"],
        "model": f"Claude（你的帳號，{written.astimezone(TW):%m/%d %H:%M} 撰寫）",
    }


def main(argv: list[str]) -> int:
    if len(argv) < 2 or argv[1] != "check":
        print(__doc__)
        return 2
    out_dir = Path(argv[2] if len(argv) > 2 else "site/data")
    data = json.loads((out_dir / FILE_NAME).read_text("utf-8"))
    news_path = out_dir / NEWS_FILE
    urls = {n["url"] for n in json.loads(news_path.read_text("utf-8"))} if news_path.exists() else None
    problems = validate(data, urls)
    for p in problems:
        print("✗", p)
    if not problems:
        print("✓ ai_summary.json 格式正確")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
