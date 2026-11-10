"""檢查手動／AI 排程更新的上游訊號檔：python -m briefing.inputs_file check [site/data]

site/data/chain_inputs.json 的格式：{鏈代號: [{name, trend, value, as_of, url}]}
- trend：up（轉強）、flat（持平）、down（轉弱）或 null（待更新）
- trend 有填的時候，as_of 要是 YYYY-MM-DD（或 YYYY-MM、YYYY），url 要是 http(s) 連結，value 要寫出數字或事實
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

FILE_NAME = "chain_inputs.json"
TRENDS = ("up", "flat", "down", None)
DATE = re.compile(r"^\d{4}(-\d{2}(-\d{2})?)?$")


def validate(data: dict, chain_ids: set[str] | None = None) -> list[str]:
    problems = []
    if not isinstance(data, dict):
        return ["整個檔案要是一個物件"]
    for cid, items in data.items():
        if cid.startswith("_"):
            continue
        if chain_ids is not None and cid not in chain_ids:
            problems.append(f"{cid}：不是 briefing/config.py 的 CHAINS 裡的鏈代號")
        if not isinstance(items, list):
            problems.append(f"{cid}：要是清單")
            continue
        for i, it in enumerate(items):
            where = f"{cid} 第 {i + 1} 項（{it.get('name', '?')}）"
            if not it.get("name"):
                problems.append(f"{where}缺少 name")
            if it.get("trend") not in TRENDS:
                problems.append(f"{where}的 trend 要是 up、flat、down 或 null")
            if not str(it.get("url", "")).startswith(("http://", "https://")):
                problems.append(f"{where}的 url 要是連結")
            if it.get("trend") is not None:
                if not DATE.match(str(it.get("as_of", ""))):
                    problems.append(f"{where}有填 trend，as_of 要是 YYYY-MM-DD、YYYY-MM 或 YYYY")
                if not it.get("value") or "待更新" in str(it.get("value")):
                    problems.append(f"{where}有填 trend，value 要寫出數字或事實")
    return problems


def main(argv: list[str]) -> int:
    if len(argv) < 2 or argv[1] != "check":
        print(__doc__)
        return 2
    out_dir = Path(argv[2] if len(argv) > 2 else "site/data")
    data = json.loads((out_dir / FILE_NAME).read_text("utf-8"))
    from . import config
    problems = validate(data, {c["id"] for c in config.CHAINS})
    for p in problems:
        print("✗", p)
    todo = sum(1 for k, v in data.items() if not k.startswith("_") for it in v if it.get("trend") is None)
    if not problems:
        print(f"✓ chain_inputs.json 格式正確（還有 {todo} 項待更新）")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
