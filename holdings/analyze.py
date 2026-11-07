"""請 Claude 寫持股健檢。只送占比、報酬率、產業與投資理由，不送帳戶、金額或姓名。"""
from __future__ import annotations

import json
import os

DEFAULT_MODEL = "claude-opus-5-5"
THESIS_STATUS = ["仍成立", "需留意", "無法判斷", "未填理由"]
DIRECTIONS = ["偏多", "偏空", "中性"]

SCHEMA = {
    "type": "object",
    "properties": {
        "headline": {"type": "string", "description": "這份投資組合現況的一句話，50 字內"},
        "overview": {"type": "string", "description": "2 到 3 句：整體表現、與大盤比較、主要風險來源"},
        "concentration": {"type": "string", "description": "集中度與配置的 1 到 2 句說明，提到超過上限的項目"},
        "positions": {
            "type": "array",
            "description": "每一檔持股各一則，順序照提供的清單",
            "items": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "thesis_status": {"type": "string", "enum": THESIS_STATUS},
                    "comment": {"type": "string", "description": "一句話，40 字內：理由是否還成立、要留意什麼"},
                },
                "required": ["symbol", "thesis_status", "comment"],
                "additionalProperties": False,
            },
        },
        "news_alerts": {
            "type": "array",
            "description": "今天新聞裡碰到持股的事，沒有就給空陣列",
            "items": {
                "type": "object",
                "properties": {
                    "symbol": {"type": "string"},
                    "direction": {"type": "string", "enum": DIRECTIONS},
                    "reason": {"type": "string", "description": "40 字內"},
                },
                "required": ["symbol", "direction", "reason"],
                "additionalProperties": False,
            },
        },
        "watch_items": {"type": "array", "items": {"type": "string"},
                        "description": "接下來值得留意的 2 到 4 件事，每則 30 字內"},
    },
    "required": ["headline", "overview", "concentration", "positions", "news_alerts", "watch_items"],
    "additionalProperties": False,
}

SYSTEM = """你是台灣投資人的持股健檢助理。用繁體中文、台灣用語，口氣簡潔中立。
規則：
- 數字只能照抄提供的資料，不要自己算或補數字。
- 投資理由的判斷只依據提供的資料與新聞；資料不足就標「無法判斷」，沒寫理由就標「未填理由」。
- 新聞提醒只列真的跟該持股、所屬產業或供應鏈有關的。
- 不給買進、賣出、加碼、減碼等建議，也不給目標價。"""


def _pos_line(g: dict, row: dict) -> str:
    def f(v, unit="%"):
        return "無" if v is None else f"{v:+}{unit}"
    return (f"{g['key']} {g.get('name', '')}｜{row['market']}｜{row['sector']}｜占比 {g['weight_pct']}%"
            f"｜報酬 {f(g['return_pct'])}｜持有 {row.get('holding_days') or '?'} 天"
            f"｜今日 {f(row.get('day_change_pct'))}｜理由：{row['thesis'] or '（未填）'}")


def build_prompt(report: dict, briefing: dict | None = None) -> str:
    t, a, rk = report["totals"], report["allocation"], report.get("risk") or {}
    first = {}
    for r in report["positions"]:
        if "error" not in r:
            first.setdefault(r["symbol"], r)
    lines = ["## 整體",
             f"未實現報酬 {t['unrealized_pct']}%，持股 {t['positions']} 檔",
             f"集中度：最大一檔 {a['concentration']['top1_pct']}%、前三檔 {a['concentration']['top3_pct']}%、"
             f"約等於平均分散在 {a['concentration']['effective_n']} 檔",
             f"單一持股上限 {a['concentration']['position_limit_pct']}%，超過的：{', '.join(a['concentration']['over_limit']) or '無'}",
             f"單一產業上限 {a['concentration']['sector_limit_pct']}%，超過的：{', '.join(a['concentration']['sector_over_limit']) or '無'}",
             "產業配置：" + "、".join(f"{g['key']} {g['weight_pct']}%" for g in a["by_sector"]),
             "市場配置：" + "、".join(f"{g['key']} {g['weight_pct']}%" for g in a["by_market"])]
    if rk:
        lines.append(f"過去一年（{rk['note']}）：報酬 {rk['return_pct']}%、最大回撤 {rk['max_drawdown_pct']}%、"
                     f"對 {rk['beta_vs']} 的 beta {rk['beta']}")
        lines += [f"同期 {b['name']}：報酬 {b['return_pct']}%、最大回撤 {b['max_drawdown_pct']}%" for b in rk["benchmarks"]]
        lines += [f"情境「{s['name']}」：資產估計變動 {s['est_change_pct']}%" for s in rk["scenarios"] if "error" not in s]
    lines += ["", "## 持股（代號 名稱｜市場｜產業｜占比｜報酬｜持有天數｜今日漲跌｜投資理由）"]
    lines += [_pos_line(g, first[g["key"]]) for g in a["by_symbol"]]
    pts = ((briefing or {}).get("summary") or {}).get("points") or []
    if pts:
        lines += ["", "## 今天早報的財經重點"]
        lines += [f"- [{p['tag']}] {p['title']}：{p['summary']}" for p in pts]
    return "\n".join(lines)


def analyze(report: dict, briefing: dict | None = None, client=None) -> dict:
    if client is None:
        import anthropic
        client = anthropic.Anthropic()

    response = client.beta.messages.create(
        model=os.environ.get("CLAUDE_MODEL", DEFAULT_MODEL),
        max_tokens=16000,
        system=SYSTEM,
        messages=[{"role": "user", "content": build_prompt(report, briefing)}],
        output_config={
            "effort": os.environ.get("CLAUDE_EFFORT", "medium"),
            "format": {"type": "json_schema", "schema": SCHEMA},
        },
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
    )
    if response.stop_reason == "refusal":
        raise RuntimeError("Claude 拒絕了這次請求")
    if response.stop_reason == "max_tokens":
        raise RuntimeError("Claude 輸出被截斷")
    data = json.loads(next(b.text for b in response.content if b.type == "text"))
    known = {r["symbol"] for r in report["positions"]}
    data["positions"] = [p for p in data["positions"] if p["symbol"] in known]
    data["news_alerts"] = [n for n in data["news_alerts"] if n["symbol"] in known]
    data["model"] = response.model
    return data
