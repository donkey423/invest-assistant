"""命令列入口：python -m papertrade.research {fetch,run,compare,request}。"""
from __future__ import annotations

import argparse
import json
import logging
import os
import time
from pathlib import Path

from . import dataset, report, request, runner, synthetic

log = logging.getLogger("papertrade.research")
DATA_DIR, RESULTS_DIR, TRIALS = "research/data", "research/results", "research/trials.json"


def _parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="python -m papertrade.research", description="Walk-forward 研究框架")
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fetch", help="抓長歷史資料，切掉保留段後存成樣本內資料集")
    f.add_argument("--out", default=DATA_DIR)
    f.add_argument("--skip-chips", action="store_true", help="不抓證交所法人資料（combo 的外資分數會缺）")
    f.add_argument("--chips-from", help="法人資料從哪一天開始抓（YYYY-MM-DD）")
    f.add_argument("--write-holdout", action="store_true", help="另外寫出保留段檔（預設不寫；該檔不進版控）")
    f.add_argument("--synthetic", action="store_true", help="開發用：不連網，產生合成資料（必須另外指定 --out）")
    f.add_argument("--days", type=int, default=2160, help="合成資料的交易日數")
    f.add_argument("--seed", type=int, default=0)
    r = sub.add_parser("run", help="跑一個或多個變體（只用樣本內資料）")
    r.add_argument("--variant", action="append", required=True)
    r.add_argument("--data", default=DATA_DIR)
    r.add_argument("--out", default=RESULTS_DIR)
    r.add_argument("--trials", default=TRIALS)
    r.add_argument("--folds", type=int, default=runner.FOLDS)
    r.add_argument("--unlock-holdout", action="store_true",
                   help=f"接上保留段（還需要環境變數 {dataset.HOLDOUT_ENV}={dataset.HOLDOUT_KEY}；須經 Brad 本人同意）")
    c = sub.add_parser("compare", help="變體對 baseline 的比較")
    c.add_argument("--base", default="baseline")
    c.add_argument("--variant", action="append", required=True)
    c.add_argument("--out", default=RESULTS_DIR)
    c.add_argument("--trials", default=TRIALS)
    c.add_argument("--holdout", action="store_true", help="比較解鎖保留段後的結果（<變體>.holdout.json）")
    q = sub.add_parser("request", help="執行請求檔（GitHub Actions 用）")
    q.add_argument("files", nargs="+")
    return ap


def cmd_fetch(args) -> dict:
    if args.chips_from and not dataset._is_date(args.chips_from):
        raise SystemExit("--chips-from 要是 YYYY-MM-DD")
    if args.synthetic:
        if Path(args.out) == Path(DATA_DIR):
            raise SystemExit("合成資料不能寫進 research/data，請用 --out 指定別的資料夾")
        full = synthetic.make_dataset(n_days=args.days, seed=args.seed)
        manifest = dataset.finalize(args.out, full, dataset.read_manifest(args.out),
                                    {"synthetic": True, "source": "synthetic", "seed": args.seed}, args.write_holdout)
    else:
        manifest = dataset.fetch(args.out, skip_chips=args.skip_chips, chips_from=args.chips_from,
                                 write_holdout=args.write_holdout, token=os.environ.get("FINMIND_TOKEN") or None)
    log.info("樣本內 %s～%s（%d 天），保留段自 %s 起 %d 天%s；涵蓋 %s", manifest["insample_start"], manifest["insample_end"],
             manifest["n_insample"], manifest["holdout_start"], manifest["n_holdout"],
             "（已另存保留段檔）" if args.write_holdout else "（沒有寫出）", json.dumps(manifest["counts"], ensure_ascii=False))
    if manifest.get("failed_symbols"):
        log.warning("抓不到股價的代號：%s", "、".join(manifest["failed_symbols"]))
    return manifest


def cmd_run(args) -> list[dict]:
    for name in args.variant:
        if name not in runner.VARIANTS:
            raise SystemExit(f"沒有登記的變體：{name}（已登記：{'、'.join(runner.VARIANTS)}）")
    ds, manifest = dataset.load_dataset(args.data, unlock_holdout=args.unlock_holdout)
    out = []
    for name in args.variant:
        t0 = time.time()
        res = runner.run_variant(name, ds, manifest, k=args.folds, unlocked=args.unlock_holdout)
        path = report.write_result(args.out, res)
        if not args.unlock_holdout:   # 保留段的結果不進試驗紀錄，樣本內的每次執行都記
            report.log_trial(args.trials, res)
        log.info("== %s（%.0f 秒）→ %s", name, time.time() - t0, path)
        for mid, m in res["methods"].items():
            a = m["all"]
            log.info("%-10s 夏普 %s  年化 %s  最大回撤 %s  交易 %d 筆", mid, report._num(a["sharpe"]), report._pct(a["cagr"]),
                     report._pct(a["max_drawdown"]), a["n_trades"])
        out.append(res)
    return out


def cmd_compare(args) -> list[dict]:
    out_dir = Path(args.out)
    suffix = ".holdout" if args.holdout else ""
    read = lambda name: json.loads((out_dir / f"{name}{suffix}.json").read_text("utf-8"))  # noqa: E731
    try:
        base = read(args.base)
    except OSError as e:
        raise SystemExit(f"找不到 {args.base} 的結果，請先 run：{e}") from e
    trials = report.read_trials(args.trials)
    out = []
    for name in args.variant:
        try:
            var = read(name)
        except OSError as e:
            raise SystemExit(f"找不到 {name} 的結果，請先 run：{e}") from e
        cmp = report.compare(base, var, trials)
        path = report.write_compare(out_dir, cmp)
        log.info("比較 %s 對 %s → %s", name, args.base, path)
        out.append(cmp)
    return out


def cmd_request(args) -> list:
    """先把所有請求檔檢查完，全部合格才開始執行。"""
    plans = [request.load_request(f) for f in args.files]
    out = []
    for argv in (a for plan in plans for a in plan):
        log.info("執行請求：%s", " ".join(argv))
        out.append(main(argv))
    return out


def main(argv=None):
    args = _parser().parse_args(argv)
    return {"fetch": cmd_fetch, "run": cmd_run, "compare": cmd_compare, "request": cmd_request}[args.cmd](args)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    main()
