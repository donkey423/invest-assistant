"""呼叫 Claude，把行情數字與新聞標題整理成早報文字。

每次更新只呼叫一次。Claude 只負責挑重點、寫一句話；數字由程式提供。
"""
from __future__ import annotations

import json
import os

DEFAULT_MODEL = "claude-opus-5-5"

TAGS = ["央行", "經濟數據", "企業", "產業", "地緣政治", "市場"]

SCHEMA = {
    "type": "object",
    "properties": {
        "headline": {"type": "string", "description": "今天市場的一句話總結，60 字內"},
        "market_comment": {"type": "string", "description": "台股與美股的 2 到 3 句說明"},
        "points": {
            "type": "array",
            "description": "3 到 6 則財經重點，最重要的放前面",
            "items": {
                "type": "object",
                "properties": {
                    "tag": {"type": "string", "enum": TAGS},
                    "title": {"type": "string", "description": "20 字內"},
                    "summary": {"type": "string", "description": "一句話說明對市場的意義，50 字內"},
                    "news_ids": {"type": "array", "items": {"type": "integer"},
                                 "description": "依據的新聞編號"},
                },
                "required": ["tag", "title", "summary", "news_ids"],
                "additionalProperties": False,
            },
        },
    },
    "required": ["headline", "market_comment", "points"],
    "additionalProperties": False,
}

SYSTEM = """你是台灣投資人的財經早報編輯。用繁體中文、台灣用語，口氣簡潔中立。
規則：
- 只根據提供的行情數字與新聞寫，不要自己補數字或事件。
- 引用漲跌幅時照抄提供的數字。
- 財經重點挑對台股、美股、匯率、利率最有影響的事，每則都要標出依據的新聞編號。
- 不給買賣建議。"""


def _fmt_quote(q: dict) -> str:
    if "error" in q:
        return f"{q['name']}：無資料"
    return (f"{q['name']} {q['last']:,}（今日 {q['change_pct']:+}%，"
            f"近五日 {q['chg_5d']:+}%，近一月 {q['chg_1m']:+}%，資料日 {q['as_of']}）")


def build_prompt(market: dict, news: list[dict]) -> str:
    lines = ["## 行情", _fmt_quote(market["taiex"])]
    lines += [_fmt_quote(q) for q in market["global"]]
    lines += ["", "## 美國 AI 股"] + [_fmt_quote(q) for q in market["ai_stocks"]]
    gauges = [q for q in market.get("gauges", []) if "error" not in q]
    if gauges:
        lines += ["", "## 市場溫度計"] + [_fmt_quote(q) for q in gauges]
    chips = market.get("chips") or {}
    if chips.get("notes"):
        inst = chips.get("institutional") or {}
        lines += ["", f"## 台股籌碼（資料日 {inst.get('date', '')}）"] + chips["notes"]
    lines += ["", "## 新聞（編號. 來源｜標題｜摘要）"]
    for i, n in enumerate(news):
        lines.append(f"{i}. {n['source']}｜{n['title']}｜{n['summary']}")
    return "\n".join(lines)


FREE_MODEL = "免費模式（未使用 AI，由程式整理）"


def _brief_pct(q: dict) -> str:
    if "error" in q or q.get("change_pct") is None:
        return f"{q['name']} 無資料"
    return f"{q['name']} {q['last']:,}（{q['change_pct']:+}%）"


def simple_summary(market: dict, news: list[dict], max_points: int = 6) -> dict:
    """不呼叫 AI 的早報：數字直接照列，重點改成各來源輪流挑的最新新聞標題。"""
    taiex = market["taiex"]
    headline = (f"台股加權指數 {taiex['last']:,}，今日 {taiex['change_pct']:+}%"
                if "error" not in taiex else "今日台股資料暫缺")
    by_sym = {q["symbol"]: q for q in market["global"]}
    us = [by_sym[s] for s in ("^GSPC", "^IXIC") if s in by_sym]
    comment = "；".join(_brief_pct(q) for q in [taiex, *us]) + "。"

    # 各新聞來源輪流取一則，避免全部來自同一個來源
    queues: dict[str, list[dict]] = {}
    for n in [n for n in news if n.get("topic", "finance") == "finance"] or news:
        queues.setdefault(n["source"], []).append(n)
    picked: list[dict] = []
    while len(picked) < max_points and any(queues.values()):
        for q in queues.values():
            if q and len(picked) < max_points:
                picked.append(q.pop(0))

    points = [{
        "tag": "市場",
        "title": n["title"],
        "summary": n["summary"] or n["source"],
        "sources": [{"title": n["title"], "url": n["url"], "source": n["source"]}],
    } for n in picked]
    return {"headline": headline, "market_comment": comment, "points": points, "model": FREE_MODEL}


def summarize(market: dict, news: list[dict], client=None) -> dict:
    if client is None and not os.environ.get("ANTHROPIC_API_KEY"):
        return simple_summary(market, news)
    if client is None:
        import anthropic
        client = anthropic.Anthropic()

    response = client.beta.messages.create(
        model=os.environ.get("CLAUDE_MODEL", DEFAULT_MODEL),
        max_tokens=16000,
        system=SYSTEM,
        messages=[{"role": "user", "content": build_prompt(market, news)}],
        output_config={
            "effort": os.environ.get("CLAUDE_EFFORT", "medium"),
            "format": {"type": "json_schema", "schema": SCHEMA},
        },
        # 若請求被安全機制拒絕，由伺服器自動改用建議的備援模型重跑
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
    )
    if response.stop_reason == "refusal":
        raise RuntimeError("Claude 拒絕了這次請求")
    if response.stop_reason == "max_tokens":
        raise RuntimeError("Claude 輸出被截斷")

    text = next(b.text for b in response.content if b.type == "text")
    data = json.loads(text)

    # 把新聞編號換成連結，網頁上可點開原文核對
    for p in data["points"]:
        p["sources"] = [
            {"title": news[i]["title"], "url": news[i]["url"], "source": news[i]["source"]}
            for i in p.pop("news_ids") if 0 <= i < len(news)
        ]
    data["model"] = response.model
    return data
