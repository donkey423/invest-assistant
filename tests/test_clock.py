import importlib.util
from datetime import datetime, timedelta, timezone
from pathlib import Path

spec = importlib.util.spec_from_file_location("clock", Path(__file__).resolve().parents[1] / "tools" / "clock.py")
clock = importlib.util.module_from_spec(spec)
spec.loader.exec_module(clock)


def utc(d, h, m):
    return datetime(2026, 11, d, h, m, tzinfo=timezone.utc)   # 2026-11-10 是週二


def test_due_fires_once_per_slot():
    assert clock.due(utc(10, 3, 59), utc(10, 4, 0)) == ["briefing.yml", "alerts.yml"]   # 台灣 12:00
    assert clock.due(utc(10, 4, 0), utc(10, 4, 1)) == []                                 # 下一分鐘不重複
    assert clock.due(utc(10, 6, 29), utc(10, 6, 31)) == ["holdings.yml"]                 # 14:30，警報已收工
    assert clock.due(utc(10, 13, 29, ), utc(10, 13, 30)) == ["alerts.yml"]              # 21:30 美股時段


def test_weekend_is_idle_and_weeknight_is_not():
    assert clock.due(utc(14, 0, 0), utc(15, 23, 59)) == []          # 週六、週日（UTC）整天沒事
    assert clock.idle(utc(13, 21, 31)) is True                      # 週六 05:31（台灣）之後收工
    assert clock.idle(utc(10, 7, 0)) is False                       # 週二下午到晚上之間只是空檔


def test_every_scheduled_workflow_exists():
    wf_dir = Path(__file__).resolve().parents[1] / ".github" / "workflows"
    for _cron, wf in clock.SCHEDULE:
        assert (wf_dir / wf).exists(), wf
        assert "workflow_dispatch" in (wf_dir / wf).read_text("utf-8"), wf
