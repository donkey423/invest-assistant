"""持股測試用的假行情與假 Claude。"""
import json
import math
from datetime import date, timedelta
from types import SimpleNamespace

LAST = {"2330.TW": 1000.0, "0050.TW": 180.0, "2454.TW": 1100.0, "NVDA": 180.0, "MSFT": 500.0,
        "USDTWD=X": 32.0, "^TWII": 22000.0, "^GSPC": 6000.0, "^SOX": 5000.0}


def fake_history(symbols, days=300, end=date(2026, 11, 6)):
    """每個代號一條確定的走勢，最後一天收在 LAST。指數與個股有共同成分，beta 才算得出來。"""
    dates = [(end - timedelta(days=days - 1 - i)).isoformat() for i in range(days)]
    common = [math.sin(i / 7) * 0.01 for i in range(days)]
    out = {}
    for k, sym in enumerate(symbols):
        if sym not in LAST:
            continue
        scale = 0.2 if sym == "USDTWD=X" else 1 + (k % 3) * 0.3
        rets = [c * scale + math.cos(i * (k + 2)) * 0.003 for i, c in enumerate(common)]
        prices = [1.0]
        for r in rets[1:]:
            prices.append(prices[-1] * (1 + r))
        f = LAST[sym] / prices[-1]
        out[sym] = (dates, [p * f for p in prices])
    return out


FAKE_ANALYSIS = {
    "headline": "半導體占比偏高，整體報酬優於大盤",
    "overview": "持股以台積電為主。",
    "concentration": "台積電超過 20% 上限。",
    "positions": [
        {"symbol": "2330", "thesis_status": "仍成立", "comment": "AI 需求延續"},
        {"symbol": "FAKE", "thesis_status": "需留意", "comment": "不存在的代號應被濾掉"},
    ],
    "news_alerts": [{"symbol": "2330", "direction": "偏多", "reason": "營收創新高"}],
    "watch_items": ["留意 Fed 會議"],
}


class FakeClient:
    def __init__(self, payload=FAKE_ANALYSIS, stop_reason="end_turn"):
        self.calls = []
        outer = self

        class _Messages:
            def create(self, **kw):
                outer.calls.append(kw)
                return SimpleNamespace(stop_reason=stop_reason, model=kw["model"],
                                       content=[SimpleNamespace(type="text", text=json.dumps(payload, ensure_ascii=False))])

        self.beta = SimpleNamespace(messages=_Messages())
