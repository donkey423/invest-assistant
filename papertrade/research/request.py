"""GitHub Actions 用的請求檔（research/requests/*.json）：嚴格檢查後轉成命令列參數。

格式（單一步驟，或 {"steps": [步驟, ...]} 依序執行）：
  {"cmd": "fetch", "args": ["--skip-chips", "--chips-from", "2019-01-01"]}
  {"cmd": "run", "variants": ["baseline"], "folds": 5}
  {"cmd": "compare", "base": "baseline", "variants": ["M1"]}
每個步驟可以多一個 "note"（給人看的說明）。
只接受白名單內的命令與鍵；輸出位置固定，不能由請求檔指定。
請求檔沒有任何辦法動到保留段：只要內容任何地方出現 holdout 字樣就整份拒絕。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .dataset import _is_date
from .runner import VARIANTS

NAME = re.compile(r"^[A-Za-z0-9_]{1,32}$")
REQUEST_PATH = re.compile(r"^research/requests/[A-Za-z0-9._-]+\.json$")
KEYS = {"fetch": {"cmd", "args", "note"}, "run": {"cmd", "variants", "folds", "note"},
        "compare": {"cmd", "base", "variant", "variants", "note"}}
MAX_STEPS = 6


class BadRequest(ValueError):
    """請求檔不合格。"""


def _strings(obj):
    """走訪 JSON 裡所有的鍵與字串值。"""
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield str(k)
            yield from _strings(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _strings(v)
    elif isinstance(obj, str):
        yield obj


def _variant(name) -> str:
    if not isinstance(name, str) or not NAME.match(name):
        raise BadRequest(f"變體名稱不合格：{name!r}")
    if name not in VARIANTS:
        raise BadRequest(f"沒有登記的變體：{name}")
    return name


def _variants(v) -> list[str]:
    if not isinstance(v, list) or not v or len(v) > 20:
        raise BadRequest("variants 必須是 1～20 個變體名稱的清單")
    return [_variant(x) for x in v]


def _step(step) -> list[str]:
    if not isinstance(step, dict):
        raise BadRequest("步驟必須是物件")
    cmd = step.get("cmd")
    if cmd not in KEYS:
        raise BadRequest(f"不允許的命令：{cmd!r}（只能是 {'、'.join(KEYS)}）")
    unknown = set(step) - KEYS[cmd]
    if unknown:
        raise BadRequest(f"{cmd} 不允許的鍵：{'、'.join(sorted(unknown))}")
    if "note" in step and not isinstance(step["note"], str):
        raise BadRequest("note 必須是字串")
    if cmd == "fetch":
        args, out, i = step.get("args", []), ["fetch"], 0
        if not isinstance(args, list) or not all(isinstance(a, str) for a in args):
            raise BadRequest("args 必須是字串清單")
        while i < len(args):
            if args[i] == "--skip-chips":
                out.append(args[i])
            elif args[i] == "--chips-from" and i + 1 < len(args) and _is_date(args[i + 1]):
                out += [args[i], args[i + 1]]
                i += 1
            else:
                raise BadRequest(f"fetch 不允許的參數：{args[i]!r}")
            i += 1
        return out
    if cmd == "run":
        out = ["run"]
        for name in _variants(step.get("variants")):
            out += ["--variant", name]
        if "folds" in step:
            if type(step["folds"]) is not int or not 2 <= step["folds"] <= 10:
                raise BadRequest("folds 必須是 2～10 的整數")
            out += ["--folds", str(step["folds"])]
        return out
    names = _variants(step["variants"]) if "variants" in step else [_variant(step.get("variant"))]
    out = ["compare", "--base", _variant(step.get("base", "baseline"))]
    for name in names:
        out += ["--variant", name]
    return out


def validate(req) -> list[list[str]]:
    """檢查請求內容，回傳要依序執行的命令列參數。不合格丟 BadRequest。"""
    if not isinstance(req, dict):
        raise BadRequest("請求檔必須是 JSON 物件")
    if any("holdout" in s.lower() for s in _strings(req)):
        raise BadRequest("請求檔不能碰保留段（holdout）：解鎖只能由 Brad 本人在本機明確操作")
    if "steps" in req:
        if set(req) - {"steps", "note"}:
            raise BadRequest("有 steps 時，最外層只能再有 note")
        steps = req["steps"]
        if not isinstance(steps, list) or not 1 <= len(steps) <= MAX_STEPS:
            raise BadRequest(f"steps 必須是 1～{MAX_STEPS} 個步驟的清單")
    else:
        steps = [req]
    return [_step(s) for s in steps]


def load_request(path) -> list[list[str]]:
    """讀請求檔並檢查。路徑必須是 research/requests/ 底下的 .json。"""
    rel = Path(path).as_posix()
    if not REQUEST_PATH.match(rel):
        raise BadRequest(f"請求檔路徑不合格：{rel}")
    try:
        req = json.loads(Path(path).read_text("utf-8"))
    except (OSError, ValueError) as e:
        raise BadRequest(f"請求檔讀不到或不是 JSON：{e}") from e
    return validate(req)
