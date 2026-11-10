"""訊號回測：每天記下各產業鏈的燈號與代表股價格，之後回頭看燈號亮起後股價的實際表現。

紀錄存在 site/data/signal_log.json（每個台灣日期一筆，同一天多次執行以最後一次為準）。
報酬一律用紀錄裡的收盤價計算：代表股等權平均報酬 − 對照指數報酬 = 超額報酬。
「命中」：轉強之後跑贏對照指數、轉弱之後跑輸對照指數。持平不算命中率。
只用排程實際記下的資料，不回補過去，所以剛開始要累積一段時間才有結果。
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

log = logging.getLogger(__name__)

LOG_FILE = "signal_log.json"
KEEP_DAYS = 400
HORIZONS = [(5, "1 週"), (20, "1 個月"), (60, "3 個月")]
LIGHTS = ("轉強", "持平", "轉弱")


def _is_tw(sym: str) -> bool:
    return sym.endswith((".TW", ".TWO")) or sym == "^TWII"


def _usable(sym: str, as_of: str | None, date: str | None) -> bool:
    """這個價格能不能記在 date 這一天。

    台股要是當天的收盤；美股、韓股只收「台股收盤時已經確定」的前一個收盤（資料日早於 date），
    避免晚上那次執行把美股盤中價記進去，也避免舊資料被記成新的一天。
    沒有資料日（測試或舊格式）就照收。
    """
    if not as_of or not date:
        return True
    return as_of == date if _is_tw(sym) else as_of < date


def snapshot(signals: dict, date: str | None = None) -> dict:
    """把這次的燈號與價格縮成一筆紀錄。"""
    chains = {}
    for c in signals.get("chains") or []:
        prices = {s["symbol"]: s["last"] for s in c.get("stocks") or []
                  if s.get("last") is not None and _usable(s["symbol"], s.get("as_of"), date)}
        p = c.get("price") or {}
        bench = p.get("bench")
        ok = bench and _usable(bench, p.get("bench_as_of"), date)
        chains[c["id"]] = {"light": c["light"], "prices": prices,
                           "bench": bench, "bench_last": p.get("bench_last") if ok else None}
    return chains


def trade_date(signals: dict) -> str | None:
    """紀錄日期＝台股代表股最新的資料日（不靠指數，指數資料偶爾會落後）。"""
    days = [s["as_of"] for c in signals.get("chains") or [] for s in c.get("stocks") or []
            if s.get("as_of") and _is_tw(s["symbol"])]
    return max(days) if days else None


def load_log(data_dir: Path) -> list[dict]:
    try:
        data = json.loads((data_dir / LOG_FILE).read_text("utf-8"))
        return data if isinstance(data, list) else []
    except (OSError, ValueError):
        return []


def update_log(entries: list[dict], date: str, signals: dict) -> list[dict]:
    """同一天多次執行：燈號以最後一次為準，價格逐檔更新（這次沒有可用價格的保留先前記下的）。"""
    snap = snapshot(signals, date)
    if not snap:
        return entries
    old = next((e for e in entries if e.get("date") == date), None)
    if old:
        for cid, c in snap.items():
            before = old["chains"].get(cid) or {}
            c["prices"] = {**before.get("prices", {}), **c["prices"]}
            if c["bench_last"] is None and before.get("bench") == c["bench"]:
                c["bench_last"] = before.get("bench_last")
    out = [e for e in entries if e.get("date") != date]
    out.append({"date": date, "chains": snap})
    out.sort(key=lambda e: e["date"])
    return out[-KEEP_DAYS:]


def _ret(then: dict, now: dict) -> float | None:
    """代表股等權平均報酬（只算兩天都有價格的股票）減對照指數報酬，單位 %。"""
    pairs = [(then["prices"][k], now["prices"][k]) for k in then.get("prices", {})
             if k in now.get("prices", {}) and then["prices"][k]]
    if not pairs or not then.get("bench_last") or not now.get("bench_last"):
        return None
    if then.get("bench") != now.get("bench"):
        return None
    stock = sum(b / a - 1 for a, b in pairs) / len(pairs)
    bench = now["bench_last"] / then["bench_last"] - 1
    return round((stock - bench) * 100, 2)


def evaluate(entries: list[dict], names: dict[str, str] | None = None) -> dict:
    names = names or {}
    stats = {}
    for h, label in HORIZONS:
        groups = {k: [] for k in LIGHTS}
        for i in range(len(entries) - h):
            then, later = entries[i], entries[i + h]
            for cid, c in then["chains"].items():
                if c["light"] not in groups or cid not in later["chains"]:
                    continue
                r = _ret(c, later["chains"][cid])
                if r is not None:
                    groups[c["light"]].append(r)
        row = {}
        for light, rs in groups.items():
            if not rs:
                row[light] = {"n": 0}
                continue
            hit = None
            if light == "轉強":
                hit = round(sum(r > 0 for r in rs) / len(rs) * 100, 1)
            elif light == "轉弱":
                hit = round(sum(r < 0 for r in rs) / len(rs) * 100, 1)
            row[light] = {"n": len(rs), "avg_excess": round(sum(rs) / len(rs), 2), "hit": hit}
        stats[label] = {"days": h, **row}

    # 燈號變化：哪天、哪條鏈、從什麼變成什麼，以及變化後到最新一筆的超額報酬
    changes = []
    latest = entries[-1] if entries else None
    for prev, cur in zip(entries, entries[1:]):
        for cid, c in cur["chains"].items():
            before = prev["chains"].get(cid)
            if before and before["light"] != c["light"]:
                changes.append({"date": cur["date"], "id": cid, "name": names.get(cid, cid),
                                "from": before["light"], "to": c["light"],
                                "excess_since": _ret(c, latest["chains"].get(cid, {})) if latest is not cur else None})
    return {
        "days_logged": len(entries),
        "since": entries[0]["date"] if entries else None,
        "horizons": stats,
        "changes": changes[-10:][::-1],
    }


def run(data_dir: Path, date: str, signals: dict | None) -> dict | None:
    """更新紀錄檔並回傳回測摘要；失敗不影響早報。"""
    if not signals:
        return None
    entries = update_log(load_log(data_dir), date, signals)
    (data_dir / LOG_FILE).write_text(json.dumps(entries, ensure_ascii=False, separators=(",", ":")), "utf-8")
    names = {c["id"]: c["name"] for c in signals.get("chains") or []}
    return evaluate(entries, names)
