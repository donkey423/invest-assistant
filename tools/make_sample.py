"""產生一份「假資料」早報，用來在沒有網路或 API key 時預覽網頁。

python tools/make_sample.py  → 寫入 site/data/latest.json（真的排程跑過就會被覆蓋）
"""
import sys
from functools import partial
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from briefing.__main__ import build  # noqa: E402
from briefing.market import build_market  # noqa: E402
from briefing.news import fetch_news  # noqa: E402
from briefing.summarize import summarize  # noqa: E402
from tests.fakes import FakeClient, fake_history, fake_parse  # noqa: E402

brief = build(
    ROOT / "site" / "data",
    market_fn=partial(build_market, history_fn=fake_history),
    news_fn=partial(fetch_news, parse=fake_parse),
    summary_fn=lambda m, n: summarize(m, n, client=FakeClient()),
)
brief["warnings"].insert(0, "這是預覽用的假資料，不是真實行情。")
import json  # noqa: E402
(ROOT / "site" / "data" / "latest.json").write_text(json.dumps(brief, ensure_ascii=False, indent=1), "utf-8")
print("已產生假資料：site/data/latest.json")
