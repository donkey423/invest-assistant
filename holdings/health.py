"""持股健檢：集中度、產業曝險，對照早報「產業鏈訊號」的燈號。全部是程式規則，不用 AI。

對應方式（一檔可以屬於多條鏈）：
1. 代號：持股代號和產業鏈代表股相同（台股去掉 .TW/.TWO 比對）。
2. 產業：持股填的「產業」和產業鏈名稱互相包含（例如「記憶體」「散熱」「航空」）。
"""
from __future__ import annotations

import re

WEAK = "轉弱"
STRONG = "轉強"


def _code(sym: str) -> str:
    s = (sym or "").strip().upper()
    return re.sub(r"\.(TW|TWO)$", "", s)


def _norm(t: str) -> str:
    return re.sub(r"[\s　與和、/（）()]+", "", (t or "").lower())


def _sector_match(sector: str, chain: dict, groups: set[str]) -> bool:
    """產業名稱互相包含才算；但「半導體」這種大分類不往下套到每條細鏈。"""
    s = _norm(sector)
    if len(s) < 2:
        return False
    names = [_norm(chain.get("name", "")), _norm(chain.get("id", ""))]
    return any(n and (s == n or n in s or (s in n and s not in groups)) for n in names)


def map_chains(rows: list[dict], chains: list[dict]) -> dict[str, list[tuple[dict, str]]]:
    """回傳 {持股代號: [(產業鏈, 對應方式 'symbol'|'sector'), ...]}。"""
    by_code: dict[str, list[dict]] = {}
    for c in chains:
        for s in c.get("stocks", []):
            by_code.setdefault(_code(s.get("symbol", "")), []).append(c)
    groups = {_norm(c.get("group", "")) for c in chains}
    out = {}
    for r in rows:
        hits: list[tuple[dict, str]] = []
        seen = set()
        for c in by_code.get(_code(r.get("quote_symbol") or r["symbol"]), []):
            if c["id"] not in seen:
                hits.append((c, "symbol")); seen.add(c["id"])
        for c in chains:
            if c["id"] not in seen and _sector_match(r.get("sector", ""), c, groups):
                hits.append((c, "sector")); seen.add(c["id"])
        out[r["symbol"]] = hits
    return out


def health(rows: list[dict], alloc: dict, risk: dict | None, briefing: dict | None, cfg) -> dict:
    signals = (briefing or {}).get("signals")
    ok = [r for r in rows if "error" not in r and r.get("value_twd")]
    total = sum(r["value_twd"] for r in ok)
    chains = (signals or {}).get("chains") or []
    conc = alloc.get("concentration", {})
    weight = {r["symbol"]: (r["value_twd"] / total if total else 0) for r in ok}
    names = {r["symbol"]: r.get("name") or r["symbol"] for r in ok}

    mapping = map_chains(ok, chains) if chains else {}
    exposure: dict[str, dict] = {}
    for sym, hits in mapping.items():
        for c, how in hits:
            e = exposure.setdefault(c["id"], {
                "id": c["id"], "name": c.get("name"), "group": c.get("group"), "light": c.get("light"),
                "why": (c.get("why") or [])[:2], "note": (c.get("price") or {}).get("note"),
                "weight": 0.0, "holdings": []})
            e["weight"] += weight[sym]
            e["holdings"].append({"symbol": sym, "name": names[sym], "by": how})
    chain_exposure = sorted(exposure.values(), key=lambda e: -e["weight"])
    for e in chain_exposure:
        e["weight_pct"] = round(e.pop("weight") * 100, 1)

    def share(pred) -> float:
        return round(sum(weight[s] for s, hits in mapping.items() if pred(hits)) * 100, 1)

    weak_pct = share(lambda h: any(c.get("light") == WEAK for c, _ in h))
    strong_pct = share(lambda h: any(c.get("light") == STRONG for c, _ in h))
    unmapped = [s for s, h in mapping.items() if not h] if chains else [r["symbol"] for r in ok]
    unmapped_pct = round(sum(weight[s] for s in unmapped) * 100, 1)

    items: list[dict] = []  # level: bad / warn / ok / info
    weak = [e for e in chain_exposure if e["light"] == WEAK]
    for e in weak:
        hs = "、".join(h["name"] for h in e["holdings"])
        why = f"（{e['why'][0]}）" if e["why"] else ""
        items.append({"level": "bad", "text": f"{hs} 屬於「{e['name']}」，產業鏈訊號轉弱{why}，占資產 {e['weight_pct']}%。"})
    for sym in conc.get("over_limit", []):
        items.append({"level": "warn", "text": f"{names.get(sym, sym)} 一檔占 {round(weight.get(sym, 0) * 100, 1)}%，超過單一持股上限 {round(cfg.POSITION_LIMIT * 100)}%。"})
    for g in alloc.get("by_sector", []):
        if g.get("over_limit"):
            items.append({"level": "warn", "text": f"產業「{g['key']}」占 {round(g["weight_pct"], 1)}%，超過產業上限 {round(cfg.SECTOR_LIMIT * 100)}%。"})
    n = conc.get("effective_n")
    if n is not None and len(ok) > 1 and n < 5:
        items.append({"level": "warn", "text": f"相當於只平均分散在 {n} 檔，漲跌會集中在少數幾檔。"})
    beta = (risk or {}).get("beta")
    if beta is not None and beta > 1.3:
        items.append({"level": "warn", "text": f"對大盤的 beta {beta}，大盤跌 10% 時持股大約跌 {round(beta * 10)}%。"})
    for e in chain_exposure:
        if e["light"] == STRONG:
            items.append({"level": "ok", "text": f"「{e['name']}」訊號轉強（{'、'.join(h['name'] for h in e['holdings'])}，占 {e['weight_pct']}%）。"})
    if not chains:
        items.append({"level": "info", "text": "這次讀不到產業鏈訊號，等早報更新後再對照。"})
    elif unmapped:
        items.append({"level": "info", "text": f"{'、'.join(names[s] for s in unmapped)}（占 {unmapped_pct}%）對不到任何產業鏈。ETF 本來就不會對上；個股可以把「產業」改成產業鏈的名稱（例如「記憶體」「散熱」）。"})
    if not any(i["level"] in ("bad", "warn") for i in items):
        items.insert(0, {"level": "ok", "text": "沒有超過集中度上限，也沒有持股在轉弱的產業鏈。"})

    return {
        "signals_at": (briefing or {}).get("generated_at") if signals else None,
        "chain_exposure": chain_exposure,
        "weak_pct": weak_pct,
        "strong_pct": strong_pct,
        "unmapped": unmapped,
        "unmapped_pct": unmapped_pct,
        "items": items,
    }
