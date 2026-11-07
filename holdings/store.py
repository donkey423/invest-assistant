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
        for r in self._req("GET", "holdings", {"select": "*", "order": "id"}) or []:
            try:
                users[r["user_id"]]["positions"].append(position_from_row(r))
            except ValueError as e:
                users[r["user_id"]]["warnings"].append(f"持股 {r.get('symbol')} 資料有誤，略過：{e}")
        for r in self._req("GET", "transactions", {"select": "*", "order": "date"}) or []:
            try:
                users[r["user_id"]]["transactions"].append(transaction_from_row(r))
            except ValueError as e:
                users[r["user_id"]]["warnings"].append(f"交易 {r.get('symbol')} {r.get('date')} 資料有誤，略過：{e}")
        for r in self._req("GET", "holdings_reports", {"select": "user_id,report"}) or []:
            self._prev[r["user_id"]] = r["report"]
        return {uid: u for uid, u in users.items() if u["positions"]}

    def previous(self, uid: str) -> dict | None:
        return self._prev.get(uid)

    def save(self, uid: str, report: dict) -> None:
        self._req("POST", "holdings_reports", {"on_conflict": "user_id"},
                  [{"user_id": uid, "report": report, "generated_at": report["generated_at"]}],
                  {"Prefer": "resolution=merge-duplicates,return=minimal"})
