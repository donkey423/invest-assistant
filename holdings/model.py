"""讀取持股明細與交易紀錄（CSV，可用中文或英文欄名）。"""
from __future__ import annotations

import csv
import re
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

# 中文欄名 → 程式內部名稱
ALIASES = {
    "代號": "symbol", "名稱": "name", "市場": "market", "幣別": "currency",
    "股數": "shares", "成本": "avg_cost", "平均成本": "avg_cost",
    "買入日期": "buy_date", "帳戶": "account", "投資理由": "thesis", "備註": "thesis",
    "產業": "sector", "買入匯率": "fx_cost",
    "日期": "date", "類型": "type", "價格": "price", "金額": "amount", "手續費": "fee",
}
TX_TYPES = {"賣出": "sell", "sell": "sell", "股息": "dividend", "dividend": "dividend"}


@dataclass
class Position:
    symbol: str            # 原始代號，例如 2330、NVDA
    shares: float
    avg_cost: float        # 每股平均成本（原幣）
    buy_date: date | None = None
    name: str = ""
    market: str = ""       # TW / US
    currency: str = ""     # TWD / USD
    account: str = ""
    thesis: str = ""
    sector: str = ""
    fx_cost: float | None = None  # 買入時匯率（外幣才需要）
    quote_symbol: str = field(default="", repr=False)  # 抓行情用的代號，例如 2330.TW

    def __post_init__(self):
        self.symbol = self.symbol.strip().upper()
        if not self.market:
            self.market = "TW" if re.match(r"^\d{4,6}[A-Z]?(\.TWO?)?$", self.symbol) else "US"
        if not self.currency:
            self.currency = "TWD" if self.market == "TW" else "USD"
        if not self.quote_symbol:
            if self.market == "TW" and "." not in self.symbol:
                self.quote_symbol = f"{self.symbol}.TW"  # 上櫃請自己寫成 xxxx.TWO
            else:
                self.quote_symbol = self.symbol
        self.sector = self.sector or "未分類"
        self.account = self.account or "未指定"


@dataclass
class Transaction:
    date: date
    symbol: str
    type: str              # sell / dividend
    shares: float = 0
    price: float = 0       # 賣出價
    avg_cost: float = 0    # 賣出那批的平均成本
    amount: float = 0      # 股息金額（原幣，稅後）
    fee: float = 0         # 手續費＋交易稅
    currency: str = ""
    account: str = ""


def _num(v: str | None) -> float | None:
    if v is None or str(v).strip() == "":
        return None
    return float(str(v).replace(",", "").replace("$", "").strip())


def _date(v: str | None) -> date | None:
    if not v or not v.strip():
        return None
    return date.fromisoformat(v.strip().replace("/", "-"))


def _rows(path: Path) -> list[dict]:
    with open(path, encoding="utf-8-sig", newline="") as f:  # utf-8-sig：Excel 存的 CSV 開頭有 BOM
        out = []
        for i, raw in enumerate(csv.DictReader(f), start=2):
            row = {ALIASES.get(k.strip(), k.strip()): (v or "").strip() for k, v in raw.items() if k}
            if not any(row.values()) or row.get("symbol", "").startswith("#"):
                continue
            row["_line"] = i
            out.append(row)
        return out


def position_from_row(r: dict) -> Position:
    """一列資料（CSV 或資料庫，欄名已轉成英文）→ Position。"""
    r = {k: ("" if v is None else str(v).strip()) for k, v in r.items()}
    shares, cost = _num(r.get("shares")), _num(r.get("avg_cost"))
    if not r.get("symbol") or shares is None or cost is None:
        raise ValueError("代號、股數、成本都要填")
    return Position(
        symbol=r["symbol"], shares=shares, avg_cost=cost, buy_date=_date(r.get("buy_date")),
        name=r.get("name", ""), market=r.get("market", "").upper(),
        currency=r.get("currency", "").upper(), account=r.get("account", ""),
        thesis=r.get("thesis", ""), sector=r.get("sector", ""), fx_cost=_num(r.get("fx_cost")),
    )


def transaction_from_row(r: dict) -> Transaction:
    r = {k: ("" if v is None else str(v).strip()) for k, v in r.items()}
    t = TX_TYPES.get(r.get("type", "").lower()) or TX_TYPES.get(r.get("type", ""))
    if t is None:
        raise ValueError(f"類型只能是 賣出 或 股息，收到「{r.get('type')}」")
    if not r.get("symbol") or not r.get("date"):
        raise ValueError("日期、代號都要填")
    p = Position(symbol=r["symbol"], shares=0, avg_cost=0, currency=r.get("currency", "").upper())
    return Transaction(
        date=_date(r.get("date")), symbol=p.symbol, type=t,
        shares=_num(r.get("shares")) or 0, price=_num(r.get("price")) or 0,
        avg_cost=_num(r.get("avg_cost")) or 0, amount=_num(r.get("amount")) or 0,
        fee=_num(r.get("fee")) or 0, currency=p.currency, account=r.get("account", ""),
    )


def load_positions(path: Path) -> list[Position]:
    """讀持股明細。同一檔在不同帳戶可以分開列。"""
    out = []
    for r in _rows(path):
        try:
            out.append(position_from_row(r))
        except ValueError as e:
            raise ValueError(f"{path} 第 {r['_line']} 行：{e}") from e
    return out


def load_transactions(path: Path) -> list[Transaction]:
    if not path.exists():
        return []
    out = []
    for r in _rows(path):
        try:
            out.append(transaction_from_row(r))
        except (ValueError, TypeError) as e:
            raise ValueError(f"{path} 第 {r['_line']} 行：{e}") from e
    return out
