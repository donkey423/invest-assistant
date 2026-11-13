"""研究用長歷史資料集：抓取、切出保留段（holdout）、存檔、載入。

保留段規則（專案擁有者明定，未經他本人同意不得使用最後 20%）：
- 交易日曆＝^TWII、0050、2330 日期的聯集；前 WARMUP 個交易日是暖機，其後才是「評估日」。
- 保留段＝評估日的最後 20%。界線（holdout_start）第一次抓資料時寫進 manifest.json，之後重抓不會移動。
- 樣本內檔 insample.json.gz 不含任何日期 >= holdout_start 的資料（股價、股利、VIX、估值、法人；月營收以「可用日」判斷）。
- 保留段檔 holdout.json.gz 只有加 --write-holdout 才會寫，而且列在 .gitignore。
- 載入保留段要同時有 --unlock-holdout 與環境變數 RESEARCH_HOLDOUT_OK=brad-approved。
"""
from __future__ import annotations

import gzip
import hashlib
import json
import logging
import math
import time
import urllib.error
from bisect import bisect_left
from datetime import date, datetime, timedelta
from pathlib import Path

from .. import backtest as bt
from .. import config as C
from .. import data
from ..__main__ import TW, universe

log = logging.getLogger("papertrade.research")

START_PX = "2018-01-01"      # 股價起點
START_FM = "2017-01-01"      # FinMind 月營收／估值起點（月營收年增要前一年同月）
WARMUP = 260                 # 暖機交易日數（12-1 動能要 253 根 K 棒）
HOLDOUT_FRAC = 0.2
EXTRA_SYMBOLS = ["^TWII", "^VIX", "0050.TW"]
INSAMPLE, HOLDOUT, MANIFEST = "insample.json.gz", "holdout.json.gz", "manifest.json"
CHIPS_DIR, HOLDOUT_CHIPS_DIR = "chips", "holdout_chips"
HOLDOUT_ENV, HOLDOUT_KEY = "RESEARCH_HOLDOUT_OK", "brad-approved"
PX_FIELDS = ("open", "close", "volume", "div", "adj_close", "split")


class HoldoutLocked(RuntimeError):
    """沒有同時具備兩個解鎖條件就想讀保留段。"""


# ---------- 界線 ----------

def boundary(cal: list[str], existing: dict | None = None) -> dict:
    """由交易日曆算出暖機、樣本內、保留段的界線。existing 是舊的 manifest：有的話沿用它的 holdout_start。"""
    if len(cal) < WARMUP + 10:
        raise ValueError(f"交易日只有 {len(cal)} 天，不夠暖機 {WARMUP} 天")
    evald = cal[WARMUP:]
    n_hold = math.ceil(len(evald) * HOLDOUT_FRAC)
    hs = (existing or {}).get("holdout_start") or evald[len(evald) - n_hold]
    ins = [d for d in evald if d < hs]
    hold = [d for d in evald if d >= hs]
    if not ins:
        raise ValueError("樣本內沒有任何評估日")
    return {"first_date": cal[0], "last_date": cal[-1], "n_days": len(cal), "warmup": WARMUP, "warmup_end": cal[WARMUP - 1],
            "insample_start": ins[0], "insample_end": ins[-1], "holdout_start": hs,
            "holdout_end": hold[-1] if hold else None, "n_eval": len(evald), "n_insample": len(ins), "n_holdout": len(hold),
            "holdout_frac": round(len(hold) / len(evald), 4)}


# ---------- 切割與檢查 ----------

def split_dataset(full: dict, hs: str) -> tuple[dict, dict]:
    """把完整資料切成（樣本內, 保留段）。樣本內不含任何 >= hs 的資料。

    還原價 adj_close 會重新定基，讓樣本內最後一根的 adj_close 等於 close：
    Yahoo 的還原價乘上了「之後所有配息」的係數，不重新定基的話，保留段的配息會從水準洩漏進樣本內。
    """
    ins = {"px": {}, "rev": {}, "val": {}, "chips": {}}
    hold = {"px": {}, "rev": {}, "val": {}, "chips": {}, "adj_scale": {}}
    for sym, s in full["px"].items():
        n = bisect_left(s["dates"], hs)
        a = {f: v[:n] for f, v in s.items()}
        b = {f: v[n:] for f, v in s.items()}
        if n and "adj_close" in a and a["adj_close"][-1] and a["close"][-1]:
            k = a["close"][-1] / a["adj_close"][-1]
            a["adj_close"] = [round(x * k, 4) for x in a["adj_close"]]
            hold["adj_scale"][sym] = k
        if n:
            ins["px"][sym] = a
        if b["dates"]:
            hold["px"][sym] = b
    for code, series in full["rev"].items():
        ins["rev"][code] = {ym: v for ym, v in series.items() if bt._avail(ym) < hs}
        hold["rev"][code] = {ym: v for ym, v in series.items() if bt._avail(ym) >= hs}
    for code, col in full["val"].items():
        n = bisect_left(col["dates"], hs)
        ins["val"][code] = {f: v[:n] for f, v in col.items()}
        hold["val"][code] = {f: v[n:] for f, v in col.items()}
    for d, rows in full["chips"].items():
        (ins if d < hs else hold)["chips"][d] = rows
    return ins, hold


def leaks(ds: dict, hs: str) -> list[str]:
    """列出資料集中所有日期 >= hs 的項目（樣本內檔應該是空的）。"""
    out = []
    for sym, s in ds.get("px", {}).items():
        if s["dates"] and max(s["dates"]) >= hs:
            out.append(f"股價 {sym} 到 {max(s['dates'])}")
    for code, series in ds.get("rev", {}).items():
        bad = [ym for ym in series if bt._avail(ym) >= hs]
        if bad:
            out.append(f"月營收 {code} {max(bad)}（可用日 {bt._avail(max(bad))}）")
    for code, col in ds.get("val", {}).items():
        if col["dates"] and max(col["dates"]) >= hs:
            out.append(f"估值 {code} 到 {max(col['dates'])}")
    bad = [d for d in ds.get("chips", {}) if d >= hs]
    if bad:
        out.append(f"法人 {len(bad)} 天（到 {max(bad)}）")
    return out


def merge_dataset(ins: dict, hold: dict) -> dict:
    """樣本內＋保留段 → 完整資料（只在解鎖後使用）。"""
    out = {"px": {}, "rev": {}, "val": {}, "chips": {**ins["chips"], **hold["chips"]}}
    for sym in {*ins["px"], *hold["px"]}:
        a, b = ins["px"].get(sym), hold["px"].get(sym)
        if a and b:
            k = hold.get("adj_scale", {}).get(sym)
            a = {**a, "adj_close": [round(x / k, 4) for x in a["adj_close"]]} if k and "adj_close" in a else a
            out["px"][sym] = {f: a[f] + b[f] for f in a if f in b}
        else:
            out["px"][sym] = a or b
    for code in {*ins["rev"], *hold["rev"]}:
        out["rev"][code] = {**ins["rev"].get(code, {}), **hold["rev"].get(code, {})}
    for code in {*ins["val"], *hold["val"]}:
        a, b = ins["val"].get(code), hold["val"].get(code)
        out["val"][code] = {f: a[f] + b[f] for f in a} if a and b else (a or b)
    return out


# ---------- 存檔與載入 ----------

def _dump(obj) -> bytes:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")


def write_gz(path: Path, obj) -> str:
    """寫成 gzip JSON（mtime 固定為 0，內容相同檔案就相同），回傳未壓縮內容的 sha256。"""
    raw = _dump(obj)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as fh, gzip.GzipFile(fileobj=fh, mode="wb", mtime=0) as gz:
        gz.write(raw)
    return hashlib.sha256(raw).hexdigest()


def read_gz(path: Path):
    with gzip.open(path, "rb") as fh:
        return json.loads(fh.read().decode("utf-8"))


def read_manifest(data_dir) -> dict | None:
    try:
        return json.loads((Path(data_dir) / MANIFEST).read_text("utf-8"))
    except (OSError, ValueError):
        return None


def check_source(existing: dict | None, synthetic: bool):
    """真實資料與合成資料不可共用同一個資料夾（否則會沿用到對方的界線）。"""
    if existing and bool(existing.get("synthetic")) != synthetic:
        raise RuntimeError("資料夾裡已有另一種來源（真實／合成）的 manifest，請換一個資料夾，界線不可混用")


def finalize(out_dir, full: dict, existing: dict | None, extra: dict | None = None, write_holdout: bool = False) -> dict:
    """切出保留段、檢查、寫檔。回傳 manifest。保留段檔只有 write_holdout=True 才寫。"""
    out = Path(out_dir)
    check_source(existing, bool((extra or {}).get("synthetic")))
    b = boundary(bt.calendar(full["px"]), existing)
    hs = b["holdout_start"]
    ins, hold = split_dataset(full, hs)
    bad = leaks(ins, hs)
    if bad:  # 理論上不會發生；寧可失敗也不要寫出受污染的樣本內檔
        raise RuntimeError("樣本內資料含保留段日期：" + "；".join(bad[:5]))
    sha = write_gz(out / INSAMPLE, ins)
    if write_holdout:
        write_gz(out / HOLDOUT, hold)
    codes = list(full["rev"])
    manifest = {
        "fetched_at": datetime.now(TW).isoformat(timespec="minutes"), **b,
        "insample_sha256": sha, "holdout_written": bool(write_holdout),
        "counts": {"symbols": len(ins["px"]), "stocks": len(codes),
                   "revenue": sum(1 for c in codes if ins["rev"].get(c)),
                   "value": sum(1 for c in codes if (ins["val"].get(c) or {}).get("dates")),
                   "chip_days": len(ins["chips"]),
                   "dividend_events": sum(sum(1 for x in s.get("div", []) if x) for s in ins["px"].values())},
        "first_bar": {k: s["dates"][0] for k, s in sorted(ins["px"].items())},
        **(extra or {}),
    }
    (out / MANIFEST).write_text(json.dumps(manifest, ensure_ascii=False, indent=1), "utf-8")
    return manifest


def load_dataset(data_dir, unlock_holdout: bool = False, env: dict | None = None) -> tuple[dict, dict]:
    """讀樣本內資料，回傳（資料集, manifest）。

    unlock_holdout=True 才會接上保留段，而且環境變數 RESEARCH_HOLDOUT_OK 必須是 brad-approved，
    兩者缺一就丟 HoldoutLocked；保留段檔不存在則丟 FileNotFoundError。
    """
    import os
    p = Path(data_dir)
    manifest = read_manifest(p)
    if not manifest:
        raise FileNotFoundError(f"找不到 {p / MANIFEST}，請先執行 python -m papertrade.research fetch")
    ds = read_gz(p / INSAMPLE)
    bad = leaks(ds, manifest["holdout_start"])
    if bad:
        raise RuntimeError("樣本內檔含保留段日期，拒絕載入：" + "；".join(bad[:5]))
    if not unlock_holdout:
        return ds, manifest
    env = os.environ if env is None else env
    if env.get(HOLDOUT_ENV) != HOLDOUT_KEY:
        raise HoldoutLocked(f"保留段未解鎖：需要 --unlock-holdout 且環境變數 {HOLDOUT_ENV}={HOLDOUT_KEY}（須經 Brad 本人同意）")
    if not (p / HOLDOUT).exists():
        raise FileNotFoundError(f"保留段檔 {p / HOLDOUT} 不存在：要先用 fetch --write-holdout 產生（預設不寫）")
    return merge_dataset(ds, read_gz(p / HOLDOUT)), manifest


# ---------- 股價（Yahoo） ----------

def _yf_download(symbols: list[str], start: str, end: str):
    import yfinance as yf  # 延後匯入，測試時不需要

    return yf.download(list(symbols), start=start, end=end, interval="1d", auto_adjust=False, actions=True,
                       group_by="ticker", progress=False, threads=True)


def frame_series(df) -> dict | None:
    """單一代號的 DataFrame（Open/Close/Volume/Adj Close/Dividends/Stock Splits）→ 序列；資料不足回傳 None。"""
    s = df.dropna(subset=["Open", "Close", "Volume"])
    if len(s) < 2:
        return None
    close = [round(float(v), 4) for v in s["Close"].values]
    col = lambda name: [float(v) for v in s[name].fillna(0.0).values] if name in s else [0.0] * len(s)  # noqa: E731
    adj = [round(float(v), 4) for v in s["Adj Close"].fillna(s["Close"]).values] if "Adj Close" in s else list(close)
    return {"dates": [d.strftime("%Y-%m-%d") for d in s.index],
            "open": [round(float(v), 4) for v in s["Open"].values], "close": close,
            "volume": [int(v) for v in s["Volume"].values],
            "div": [round(v, 6) for v in col("Dividends")], "adj_close": adj,
            "split": [round(v, 6) for v in col("Stock Splits")]}


def fetch_prices(symbols, start: str, end: str, download=None, chunk: int = 25, retries: int = 3,
                 sleep=time.sleep) -> tuple[dict, list[str]]:
    """分批抓日線＋現金股利。回傳（{代號: 序列}, 抓不到的代號）。end 不含當天。"""
    download = download or _yf_download
    symbols = list(dict.fromkeys(symbols))
    out = {}
    for k in range(0, len(symbols), chunk):
        todo = symbols[k:k + chunk]
        for attempt in range(retries):
            try:
                df = download(todo, start, end)
            except Exception as e:  # noqa: BLE001 整批失敗就重試
                log.warning("Yahoo 第 %d 批第 %d 次失敗：%s", k // chunk + 1, attempt + 1, e)
                df = None
            for sym in list(todo):
                try:
                    s = frame_series(df[sym]) if df is not None else None
                except Exception as e:  # noqa: BLE001 單一代號失敗不影響整體
                    log.warning("抓不到 %s：%s", sym, e)
                    s = None
                if s:
                    out[sym] = s
                    todo.remove(sym)
            if not todo:
                break
            if attempt < retries - 1:
                sleep(5 * (attempt + 1))
        sleep(1)
    return out, [s for s in symbols if s not in out]


def clip_px(px: dict, last_day: str) -> dict:
    """丟掉 last_day 之後的 K 棒（盤中還沒收盤的那一根）。"""
    out = {}
    for k, s in px.items():
        n = sum(1 for d in s["dates"] if d <= last_day)
        if n:
            out[k] = {f: v[:n] for f, v in s.items()}
    return out


# ---------- FinMind 與證交所 ----------

def retrying(get, sleep=time.sleep, waits=(5, 30, 120), limit_waits=(60, 300, 900, 1800), limit_budget: float = 4500):
    """包一層重試：HTTP 402／429（流量上限）照 limit_waits 等待，其他錯誤照 waits；都用完才把例外丟出去。

    流量上限的等待時間所有請求合計最多 limit_budget 秒，用完之後遇到 402／429 就直接放棄，免得整個工作卡到逾時。
    """
    budget = [limit_budget]

    def wrapped(url: str):
        left, left_limit = list(waits), list(limit_waits)
        while True:
            try:
                return get(url)
            except urllib.error.HTTPError as e:
                limited = e.code in (402, 429)
                queue = left_limit if limited else left
                if not queue or (limited and budget[0] < queue[0]):
                    raise
                wait = queue.pop(0)
                if limited:
                    budget[0] -= wait
                log.warning("HTTP %s，等 %d 秒後重試", e.code, wait)
                sleep(wait)
            except Exception:  # noqa: BLE001 連線逾時等暫時性錯誤
                if not left:
                    raise
                sleep(left.pop(0))
    return wrapped


def value_columns(rows: list[dict]) -> dict:
    """FinMind TaiwanStockPER 的每日列 → 欄位式 {"dates", "pe", "pb", "dy"}（舊到新，缺值為 None）。"""
    f = lambda r, k: round(float(r[k]), 4) if r.get(k) not in (None, "") else None  # noqa: E731
    rows = sorted((r for r in rows if r.get("date")), key=lambda r: r["date"])
    return {"dates": [r["date"] for r in rows], "pe": [f(r, "PER") for r in rows],
            "pb": [f(r, "PBR") for r in rows], "dy": [f(r, "dividend_yield") for r in rows]}


def fetch_fundamentals(codes, get=data.get_json, sleep=time.sleep, pause: float = 1.0, token: str | None = None,
                       start: str = START_FM) -> tuple[dict, dict, dict]:
    """FinMind 月營收與每日估值。回傳（rev, val, coverage）。

    未登入的 FinMind 每小時約 300 次：每次請求之間停 pause 秒，遇 402／429 退避重試；
    回傳空的再試一次，仍然空就當作這檔沒有資料並記在 coverage。
    """
    g = retrying(get, sleep)
    fetch = (lambda url: g(url + "&token=" + token)) if token else g
    rev, val, miss = {}, {}, {"revenue_missing": [], "value_missing": []}
    empty = 0  # 連續拿到空資料的次數：太多次代表來源整個不通，就不再逐一重試
    for code in codes:
        got = {}
        for ds in ("TaiwanStockMonthRevenue", "TaiwanStockPER"):
            rows = bt.finmind(ds, code, start, fetch)
            sleep(pause)
            if not rows and empty < 6:
                sleep(10)
                rows = bt.finmind(ds, code, start, fetch)
                sleep(pause)
            empty = 0 if rows else empty + 1
            got[ds] = rows
        rev[code] = {ym: round(v, 2) for ym, v in bt.revenue_series(got["TaiwanStockMonthRevenue"]).items()}
        val[code] = value_columns(got["TaiwanStockPER"])
        if not rev[code]:
            miss["revenue_missing"].append(code)
        if not val[code]["dates"]:
            miss["value_missing"].append(code)
    return rev, val, miss


def fetch_chips(days: list[str], cache_dir, codes, get=data.get_json, sleep=time.sleep, pause: float = 2.5,
                waits=(10, 30, 90), max_fail: int = 8) -> tuple[dict, list[str]]:
    """證交所 T86 逐日抓法人買賣超（只留選股池的代號）。回傳（{日期: {代號: {foreign, trust}}}, 抓不到的日期）。

    每天一個快取檔（cache_dir/YYYY-MM-DD.json），重跑時已有的日期不再抓，所以中斷後可以接著跑。
    連續 max_fail 天都抓不到就停手（多半是被證交所暫時擋下），剩下的留給下次。
    """
    cache = Path(cache_dir)
    cache.mkdir(parents=True, exist_ok=True)
    keep, out, missing, streak = set(codes), {}, [], 0
    for i, d in enumerate(days):
        f = cache / f"{d}.json"
        if f.exists():
            try:
                out[d] = json.loads(f.read_text("utf-8"))
                continue
            except ValueError:
                pass
        if streak >= max_fail:
            missing.append(d)
            continue
        rows = {}
        for wait in (0, *waits):
            if wait:
                sleep(wait)
            try:
                rows = data.parse_t86(get(data.T86_URL.format(d=d.replace("-", ""))))
            except Exception as e:  # noqa: BLE001
                log.warning("T86 %s 失敗：%s", d, e)
                rows = {}
            sleep(pause)
            if rows:
                break
        rows = {c: {"foreign": int(r["foreign"]), "trust": int(r["trust"])} for c, r in rows.items() if c in keep}
        if rows:
            f.write_text(json.dumps(rows, separators=(",", ":")), "utf-8")
            out[d], streak = rows, 0
        else:
            missing.append(d)
            streak += 1
            if streak == max_fail:
                log.warning("T86 連續 %d 天抓不到，先停手；重跑會從快取接著抓", max_fail)
        if (i + 1) % 100 == 0:
            log.info("法人資料 %d/%d 天", i + 1, len(days))
    return out, missing


# ---------- 主流程 ----------

def fetch(out_dir, *, now: datetime | None = None, download=None, get=data.get_json, sleep=time.sleep,
          skip_chips: bool = False, chips_from: str | None = None, write_holdout: bool = False,
          universe_fn=universe, token: str | None = None) -> dict:
    """抓完整歷史 → 定界線 → 切掉保留段 → 寫 insample.json.gz 與 manifest.json。回傳 manifest。"""
    out = Path(out_dir)
    now = now or datetime.now(TW)
    sym = universe_fn()[0]
    symbols = list(dict.fromkeys([*sym.values(), *(b["symbol"] for b in C.BENCHMARKS), *EXTRA_SYMBOLS]))
    end = (now.date() + timedelta(days=1)).isoformat()
    px, failed = fetch_prices(symbols, START_PX, end, download=download, sleep=sleep)
    last = now.date().isoformat() if now.hour >= 15 else (now.date() - timedelta(days=1)).isoformat()
    px = clip_px(px, last)
    if "^TWII" not in px:
        raise RuntimeError("抓不到台股加權指數，中止")
    existing = read_manifest(out)
    check_source(existing, False)
    b = boundary(bt.calendar(px), existing)
    hs = b["holdout_start"]
    log.info("交易日 %s～%s 共 %d 天；樣本內 %s～%s；保留段自 %s 起（%d 天，不寫入樣本內檔）",
             b["first_date"], b["last_date"], b["n_days"], b["insample_start"], b["insample_end"], hs, b["n_holdout"])
    rev, val, miss = fetch_fundamentals(list(sym), get=get, sleep=sleep, token=token)
    chips, chips_missing = {}, []
    if not skip_chips:
        cal = bt.calendar(px)
        first = chips_from or cal[max(0, WARMUP - 6)]
        codes = [s.split(".")[0] for s in sym.values()]
        chips, chips_missing = fetch_chips([d for d in cal if first <= d < hs], out / CHIPS_DIR, codes, get=get, sleep=sleep)
        if write_holdout:  # 保留段的法人資料另放一個不進版控的快取
            more, _ = fetch_chips([d for d in cal if d >= max(hs, first)], out / HOLDOUT_CHIPS_DIR, codes, get=get, sleep=sleep)
            chips.update(more)
    extra = {"source": "yahoo+finmind+twse", "start_px": START_PX, "start_finmind": START_FM,
             "failed_symbols": failed, "coverage": {**miss, "chips_skipped": bool(skip_chips), "chips_from": chips_from,
                                                    "chips_missing_days": len(chips_missing),
                                                    "chips_missing_sample": chips_missing[:20]}}
    return finalize(out, {"px": px, "rev": rev, "val": val, "chips": chips}, existing, extra, write_holdout)


def manifest_hash(manifest: dict) -> str:
    """資料集的識別碼：樣本內內容的 sha256 前 16 碼。"""
    return str(manifest.get("insample_sha256") or "")[:16]


def _is_date(s: str) -> bool:
    try:
        return date.fromisoformat(s).isoformat() == s
    except (TypeError, ValueError):
        return False
