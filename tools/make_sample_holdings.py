"""用範例持股與假行情產生 site/data/private/holdings.json，預覽「我的資產」頁。

python tools/make_sample_holdings.py [--force]
已有真的 holdings.json 時不會覆蓋，除非加 --force。
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from holdings.__main__ import build  # noqa: E402
from holdings.analyze import analyze  # noqa: E402
from tests.fakes_holdings import FakeClient, fake_history  # noqa: E402

out = ROOT / "site" / "data" / "private"
if (out / "holdings.json").exists() and "--force" not in sys.argv:
    sys.exit(f"{out / 'holdings.json'} 已存在，不覆蓋（要覆蓋請加 --force）")
ex = ROOT / "holdings" / "examples"
rep = build(ex / "holdings.example.csv", out, history_fn=fake_history,
            analyze_fn=lambda r, b: analyze(r, b, client=FakeClient()),
            tx_csv=ex / "transactions.example.csv", briefing_json=ROOT / "site" / "data" / "latest.json",
            now=datetime(2026, 11, 7, 8, 0, tzinfo=timezone(timedelta(hours=8))))
import json  # noqa: E402
rep["warnings"].insert(0, "這是預覽用的範例持股與假行情，不是你的資料。")
(out / "holdings.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1), "utf-8")
print(f"已產生假資料：{out / 'holdings.json'}（總市值 {rep['totals']['value_twd']:,} 元）")
