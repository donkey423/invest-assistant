"""持股的資料庫存取。目前是 Supabase；之後要換成自架資料庫，只要寫一個有同樣三個方法的類別。

    load()          → {user_id: {"positions": [...], "transactions": [...], "warnings": [...]}}
    previous(uid)   → 上一份報告（沒有就 None），AI 失敗時沿用它的文字分析
    save(uid, rep)  → 寫入這個使用者最新的報告

只用標準函式庫（urllib），不必多裝套件。用 secret／service_role 金鑰，只放在 GitHub Secrets，絕不放前端。
"""
from __future__ import annotations

import json
import logging
import os
import urllib.parse
import urllib.request
from collections import defaultdict

from .model import position_from_row, transaction_from_row

log = logging.getLogger(__name__)


class SupabaseStore:
    def __init__(self, url: str, key: str, opener=None):
        self.base = url.rstrip("/") + "/rest/v1"
        self.headers = {"apikey": key, "Content-Type": "application/json"}
        if key.startswith("eyJ"):  # 舊式 JWT 金鑰要放 Authorization；新式 sb_secret_ 只要 apikey
            self.headers["Authorization"] = f"Bearer {key}"
        self._open = opener or urllib.request.urlopen
        self._prev: dict[str, dict] = {}

    @classmethod
    def from_env(cls) -> "SupabaseStore":
        url, key = os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_SECRET_KEY")
        if not url or not key:
            raise SystemExit("需要環境變數 SUPABASE_URL 與 SUPABASE_SECRET_KEY")
        return cls(url, key)

    def _req(self, method: str, path: str, query: dict | None = None, body=None, extra: dict | None = None):
        url = f"{self.base}/{path}" + (f"?{urllib.parse.urlencode(query)}" if query else "")
        data = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method, headers={**self.headers, **(extra or {})})
        with self._open(req, timeout=30) as res:
            raw = res.read()
            return json.loads(raw) if raw else None

    def load(self) -> dict:
        users: dict = defaultdict(lambda: {"positions": [], "transactions": [], "warnings": []})
        _fill(users, self._req("GET", "holdings", {"select": "*", "order": "id"}) or [],
              self._req("GET", "transactions", {"select": "*", "order": "date"}) or [])
        for r in self._req("GET", "holdings_reports", {"select": "user_id,report"}) or []:
            self._prev[r["user_id"]] = r["report"]
        return {uid: u for uid, u in users.items() if u["positions"]}

    def previous(self, uid: str) -> dict | None:
        return self._prev.get(uid)

    def save(self, uid: str, report: dict) -> None:
        self._req("POST", "holdings_reports", {"on_conflict": "user_id"},
                  [{"user_id": uid, "report": report, "generated_at": report["generated_at"]}],
                  {"Prefer": "resolution=merge-duplicates,return=minimal"})


class EdgeStore:
    """在 GitHub Actions 裡用 OIDC 身分證明呼叫 Supabase 的 holdings-sync 函式，不需要任何密鑰。"""

    AUDIENCE = "invest-assistant-holdings"

    def __init__(self, function_url: str, token: str, opener=None):
        self.url = function_url
        self.headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
        self._open = opener or urllib.request.urlopen
        self._prev: dict[str, dict] = {}

    @classmethod
    def from_actions(cls, supabase_url: str, opener=None) -> "EdgeStore":
        req_url, req_token = os.environ.get("ACTIONS_ID_TOKEN_REQUEST_URL"), os.environ.get("ACTIONS_ID_TOKEN_REQUEST_TOKEN")
        if not req_url or not req_token:
            raise SystemExit("不在 GitHub Actions 裡（或 workflow 沒開 id-token: write），也沒有 SUPABASE_SECRET_KEY")
        sep = "&" if "?" in req_url else "?"
        req = urllib.request.Request(f"{req_url}{sep}audience={cls.AUDIENCE}",
                                     headers={"Authorization": f"Bearer {req_token}"})
        with (opener or urllib.request.urlopen)(req, timeout=30) as res:
            token = json.loads(res.read())["value"]
        return cls(supabase_url.rstrip("/") + "/functions/v1/holdings-sync", token, opener)

    def _call(self, method: str, body=None):
        data = json.dumps(body, ensure_ascii=False).encode() if body is not None else None
        req = urllib.request.Request(self.url, data=data, method=method, headers=self.headers)
        with self._open(req, timeout=60) as res:
            return json.loads(res.read() or b"null")

    def load(self) -> dict:
        d = self._call("GET")
        users: dict = defaultdict(lambda: {"positions": [], "transactions": [], "warnings": []})
        _fill(users, d.get("holdings") or [], d.get("transactions") or [])
        for r in d.get("reports") or []:
            self._prev[r["user_id"]] = r["report"]
        return {uid: u for uid, u in users.items() if u["positions"]}

    def previous(self, uid: str) -> dict | None:
        return self._prev.get(uid)

    def save(self, uid: str, report: dict) -> None:
        self._call("POST", {"user_id": uid, "report": report, "generated_at": report["generated_at"]})


def _fill(users, holdings, transactions) -> None:
    for r in holdings:
        if r.get("removed_at"):  # 網站上刪除的持股（軟刪除）
            continue
        try:
            users[r["user_id"]]["positions"].append(position_from_row(r))
        except ValueError as e:
            users[r["user_id"]]["warnings"].append(f"持股 {r.get('symbol')} 資料有誤，略過：{e}")
    for r in transactions:
        try:
            users[r["user_id"]]["transactions"].append(transaction_from_row(r))
        except ValueError as e:
            users[r["user_id"]]["warnings"].append(f"交易 {r.get('symbol')} {r.get('date')} 資料有誤，略過：{e}")


def store_from_env(supabase_url: str):
    """有 SUPABASE_SECRET_KEY 就直接連資料庫；否則在 GitHub Actions 裡用身分證明走 holdings-sync。"""
    if os.environ.get("SUPABASE_SECRET_KEY"):
        return SupabaseStore(os.environ.get("SUPABASE_URL") or supabase_url, os.environ["SUPABASE_SECRET_KEY"])
    return EdgeStore.from_actions(os.environ.get("SUPABASE_URL") or supabase_url)
