"""測試與畫面預覽用的假資料。數字是隨機產生的，不是真實行情。"""
from __future__ import annotations

import json
import math
import random
from datetime import date, timedelta
from types import SimpleNamespace

BASE = {"^TWII": 27000, "^GSPC": 6700, "^IXIC": 23000, "^N225": 50000, "^KS11": 4000,
        "^HSI": 26000, "000001.SS": 3950, "^GDAXI": 24000, "^FTSE": 9700, "^NSEI": 25800,
        "NVDA": 190, "MSFT": 500, "GOOGL": 280, "META": 620, "AMZN": 240, "AMD": 250,
        "AVGO": 350, "TSM": 300}


def fake_history(symbols, days: int = 270, seed: int = 7):
    out = {}
    start = date(2026, 11, 6) - timedelta(days=int(days * 1.45))
    for sym in symbols:
        rnd = random.Random(f"{seed}-{sym}")
        price, closes, dates, d = BASE.get(sym, 100) * 0.8, [], [], start
        while len(closes) < days:
            d += timedelta(days=1)
            if d.weekday() >= 5:
                continue
            price *= math.exp(rnd.gauss(0.0009, 0.013))
            closes.append(price)
            dates.append(d.isoformat())
        out[sym] = (dates, closes)
    return out


FAKE_NEWS = [
    ("Fed 下月升息機率降至兩成，市場押注 12 月按兵不動", "Google 新聞 Fed"),
    ("10 月非農新增就業 16.5 萬人，失業率 4.1%", "Google 新聞 美股"),
    ("台積電 10 月營收年增 32%，創單月新高", "鉅亨網 台股"),
    ("油價連三漲，布蘭特原油站上每桶 80 美元", "Google 新聞 財經"),
    ("NVIDIA 新一代 AI 晶片下月出貨，供應鏈拉貨轉強", "Google 新聞 美股"),
    ("央行理監事會前夕，總裁：房市管制不會鬆綁", "中央社 財經"),
    ("外資昨賣超台股 85 億元，集中在電子權值股", "鉅亨網 台股"),
    ("日圓貶破 155，日本財務省口頭干預", "Google 新聞 財經"),
    ("以色列與伊朗衝突升溫，油價盤中跳漲", "Google 新聞 國際"),
    ("歐盟對中國電動車加徵關稅", "Google 新聞 地緣政治"),
    ("俄烏停火談判破局，普丁拒絕撤軍", "中央社 國際"),
    ("OpenAI 發表新模型，企業版價格下調", "Google 新聞 AI"),
    ("輝達黃仁勳：AI 資料中心需求明年翻倍", "Google 新聞 AI 產業"),
    ("美國議員提案限制 AI 晶片出口", "中央社 科技"),
]


def fake_parse(url):
    from briefing.config import NEWS_FEEDS
    name = next(f["name"] for f in NEWS_FEEDS if f["url"] == url)
    entries = [{"title": t, "summary": "", "link": f"https://example.com/{i}",
                "published_parsed": (2026, 11, 6, 22, i, 0)}
               for i, (t, src) in enumerate(FAKE_NEWS) if src == name]
    return SimpleNamespace(entries=entries)


FAKE_SUMMARY = {
    "headline": "就業數據降溫、Fed 升息預期退燒，科技股反彈帶動台股收紅",
    "market_comment": "美國非農就業低於預期，市場押注 Fed 12 月不升息，那斯達克走強。台股在台積電營收創高帶動下收紅，但外資仍站在賣方。",
    "points": [
        {"tag": "央行", "title": "Fed 下月升息機率降至兩成", "summary": "就業降溫讓升息壓力減輕，有利科技股評價。", "news_ids": [0, 1]},
        {"tag": "企業", "title": "台積電 10 月營收創新高", "summary": "AI 需求延續，支撐台股權值股。", "news_ids": [2]},
        {"tag": "市場", "title": "外資賣超台股 85 億", "summary": "籌碼面偏弱，指數上攻需觀察外資回補。", "news_ids": [6]},
        {"tag": "地緣政治", "title": "油價連三漲站上 80 美元", "summary": "通膨疑慮升溫，留意航運與塑化類股。", "news_ids": [3]},
    ],
}


class FakeClient:
    """模擬 anthropic.Anthropic()，回傳固定的摘要 JSON。"""

    def __init__(self, payload=FAKE_SUMMARY, stop_reason="end_turn"):
        self.calls = []
        payload, stop = payload, stop_reason
        outer = self

        class _Messages:
            def create(self, **kw):
                outer.calls.append(kw)
                return SimpleNamespace(
                    stop_reason=stop, model=kw["model"],
                    content=[SimpleNamespace(type="text", text=json.dumps(payload, ensure_ascii=False))])

        self.beta = SimpleNamespace(messages=_Messages())
