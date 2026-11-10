"""準時鐘：GitHub 自己的排程在這個 repo 常常晚好幾個小時，這支程式在一個長時間執行的工作裡
每分鐘看一次時間，到點就用 `gh workflow run` 觸發對應的 workflow。

用法（在 GitHub Actions 裡）：python tools/clock.py --minutes 330
- 時刻表 SCHEDULE 用和 workflow 檔案相同的 cron 寫法（UTC）。
- 不記狀態：只觸發「上次檢查之後到現在」之間到點的項目，重新啟動不會補跑也不會重複。
- 跑滿 --minutes 分鐘後結束並回傳 0；接下來 12 小時都沒有事情要做（週末）就回傳 3，呼叫端不再接力。
"""
from __future__ import annotations

import argparse
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone

# (cron「分 時 * * 星期」，UTC, workflow 檔名)。台灣時間 = UTC+8。
SCHEDULE = [
    ("0 4 * * 1-5", "briefing.yml"),        # 12:00 早報
    ("0 6 * * 1-5", "briefing.yml"),        # 14:00 台股收盤後
    ("0 14 * * 1-5", "briefing.yml"),       # 22:00 美股開盤前後
    ("*/30 1-5 * * 1-5", "alerts.yml"),     # 台股 09:00–13:30 每 30 分鐘
    ("*/30 13-20 * * 1-5", "alerts.yml"),   # 美股 21:00–04:30 每 30 分鐘
    ("30 6 * * 1-5", "holdings.yml"),       # 14:30 持股損益
    ("30 21 * * 1-5", "holdings.yml"),      # 05:30 持股損益（美股收盤後）
    ("30 10 * * 1-5", "papertrade.yml"),    # 18:30 模擬帳戶
]
IDLE_HOURS = 12


def _field(expr: str, lo: int, hi: int) -> set[int]:
    out: set[int] = set()
    for part in expr.split(","):
        rng, _, step = part.partition("/")
        if rng == "*":
            a, b = lo, hi
        elif "-" in rng:
            a, b = (int(x) for x in rng.split("-"))
        else:
            a = b = int(rng)
        out |= set(range(a, b + 1, int(step) if step else 1))
    return out


def matches(cron: str, t: datetime) -> bool:
    """t 是 UTC 時間。只支援「分 時 * * 星期」（星期 0 = 週日）。"""
    minute, hour, _dom, _mon, dow = cron.split()
    return (t.minute in _field(minute, 0, 59) and t.hour in _field(hour, 0, 23)
            and (t.weekday() + 1) % 7 in _field(dow, 0, 6))


def due(prev: datetime, now: datetime, schedule=SCHEDULE) -> list[str]:
    """prev（不含）到 now（含）之間到點的 workflow，不重複，依時刻表順序。"""
    out: list[str] = []
    t = prev.replace(second=0, microsecond=0) + timedelta(minutes=1)
    while t <= now:
        for cron, wf in schedule:
            if wf not in out and matches(cron, t):
                out.append(wf)
        t += timedelta(minutes=1)
    return out


def idle(now: datetime, hours: int = IDLE_HOURS, schedule=SCHEDULE) -> bool:
    return not due(now, now + timedelta(hours=hours), schedule)


def dispatch(wf: str) -> None:
    r = subprocess.run(["gh", "workflow", "run", wf, "--ref", "main"], capture_output=True, text=True)
    print(f"{datetime.now(timezone.utc):%H:%M} UTC 觸發 {wf}：{'OK' if r.returncode == 0 else r.stderr.strip()}", flush=True)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--minutes", type=int, default=330)
    args = ap.parse_args()
    start = prev = datetime.now(timezone.utc)
    print(f"準時鐘啟動 {start:%Y-%m-%d %H:%M} UTC，預計執行 {args.minutes} 分鐘", flush=True)
    while True:
        now = datetime.now(timezone.utc)
        for wf in due(prev, now):
            dispatch(wf)
        prev = now
        if idle(now):
            print("接下來 12 小時沒有排程（週末），結束。下個交易日早上的 AI 摘要會重新啟動。", flush=True)
            return 3
        if now - start >= timedelta(minutes=args.minutes):
            return 0
        time.sleep(60 - datetime.now(timezone.utc).second % 60 + 1)


if __name__ == "__main__":
    sys.exit(main())
