from __future__ import annotations

import json
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from tradeops.app.models import OrderSide, PortfolioState


class TlhReplacementOption(BaseModel):
    model_config = ConfigDict(frozen=True)

    ticker: str
    issuer: str | None = None
    bucket: str
    exposure: str | None = None
    leverage: str | None = None
    notes: list[str] = Field(default_factory=list)


class TlhCandidate(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    market_value: Decimal | None = None
    loss_dollars: Decimal
    loss_percent: Decimal | None = None
    wash_sale_watch: bool = False
    recent_buy_dates: list[datetime] = Field(default_factory=list)
    replacement_status: Literal["clean", "gray", "none", "unmapped"]
    replacement_options: list[TlhReplacementOption] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class DailyTlhInput(BaseModel):
    model_config = ConfigDict(frozen=True)

    as_of: datetime
    account_number: str | None = None
    equity: Decimal | None = None
    cash: Decimal | None = None
    open_orders: int = 0
    candidate_count: int = 0
    total_visible_losses: Decimal = Decimal("0")
    candidates: list[TlhCandidate] = Field(default_factory=list)


def load_tlh_etf_map(path: str | Path) -> dict:
    return json.loads(Path(path).read_text())


def _normalize_symbol(value: str | None) -> str | None:
    if value is None:
        return None
    symbol = value.strip().upper()
    return symbol or None


def _recent_buy_dates(portfolio: PortfolioState, as_of: datetime, lookback_days: int) -> dict[str, list[datetime]]:
    cutoff = as_of - timedelta(days=lookback_days)
    buy_dates: dict[str, list[datetime]] = {}

    for activity in portfolio.activities:
        symbol = _normalize_symbol(activity.symbol)
        if symbol is None or activity.side != "buy" or activity.occurred_at is None:
            continue
        if activity.occurred_at < cutoff:
            continue
        buy_dates.setdefault(symbol, []).append(activity.occurred_at)

    for order in portfolio.recent_orders:
        symbol = _normalize_symbol(order.symbol)
        if symbol is None or order.side is not OrderSide.BUY:
            continue
        event_time = order.filled_at or order.created_at
        if event_time is None or event_time < cutoff:
            continue
        buy_dates.setdefault(symbol, []).append(event_time)

    for dates in buy_dates.values():
        dates.sort(reverse=True)
    return buy_dates


def _replacement_lookup(etf_map: dict) -> dict[str, dict]:
    lookup: dict[str, dict] = {}
    for bucket, payload in etf_map.get("asset_classes", {}).items():
        etfs = payload.get("etfs", [])
        for etf in etfs:
            ticker = _normalize_symbol(etf.get("ticker"))
            if ticker is None:
                continue
            lookup[ticker] = {
                "bucket": bucket,
                "description": payload.get("description"),
                "exposure": payload.get("exposure"),
                "leverage": payload.get("leverage"),
                "entries": etfs,
                "notes": list(etf.get("notes", [])),
            }
    return lookup


def _replacement_status(symbol: str, info: dict | None) -> tuple[str, list[TlhReplacementOption], list[str]]:
    if info is None:
        return "unmapped", [], ["No local ETF TLH mapping is available for this symbol."]

    notes = list(info.get("notes", []))
    entries = info.get("entries", [])
    options: list[TlhReplacementOption] = []
    gray = False
    blocked = False

    for entry in entries:
        ticker = _normalize_symbol(entry.get("ticker"))
        if ticker is None:
            continue
        entry_notes = list(entry.get("notes", []))
        note_text = " ".join(entry_notes).lower()
        if ticker == symbol:
            if "gray" in note_text:
                gray = True
            if "do not substitute" in note_text:
                blocked = True
            continue
        if "gray" in note_text:
            gray = True
        options.append(
            TlhReplacementOption(
                ticker=ticker,
                issuer=entry.get("issuer"),
                bucket=info["bucket"],
                exposure=info.get("exposure"),
                leverage=info.get("leverage"),
                notes=entry_notes,
            )
        )

    if blocked and not options:
        return "none", [], notes or ["No alternate ETF is listed in the local TLH map."]
    if gray:
        return "gray", options, notes
    if options:
        return "clean", options, notes
    return "none", [], notes or ["No alternate ETF is listed in the local TLH map."]


def build_daily_tlh_input(
    portfolio: PortfolioState,
    etf_map: dict,
    *,
    as_of: datetime,
    lookback_days: int = 30,
) -> DailyTlhInput:
    recent_buys = _recent_buy_dates(portfolio, as_of=as_of, lookback_days=lookback_days)
    replacements = _replacement_lookup(etf_map)
    candidates: list[TlhCandidate] = []

    for position in sorted(
        portfolio.positions,
        key=lambda item: item.unrealized_pl or Decimal("0"),
    ):
        if position.unrealized_pl is None or position.unrealized_pl >= 0:
            continue
        symbol = position.symbol.upper()
        replacement_status, replacement_options, notes = _replacement_status(symbol, replacements.get(symbol))
        candidate = TlhCandidate(
            symbol=symbol,
            market_value=position.market_value,
            loss_dollars=abs(position.unrealized_pl),
            loss_percent=(abs(position.unrealized_plpc) * Decimal("100")) if position.unrealized_plpc is not None else None,
            wash_sale_watch=bool(recent_buys.get(symbol)),
            recent_buy_dates=recent_buys.get(symbol, []),
            replacement_status=replacement_status,  # type: ignore[arg-type]
            replacement_options=replacement_options,
            notes=notes,
        )
        candidates.append(candidate)

    total_visible_losses = sum((candidate.loss_dollars for candidate in candidates), Decimal("0"))
    return DailyTlhInput(
        as_of=as_of,
        account_number=portfolio.account.account_number or portfolio.account.account_id,
        equity=portfolio.account.equity,
        cash=portfolio.account.cash,
        open_orders=len(portfolio.open_orders),
        candidate_count=len(candidates),
        total_visible_losses=total_visible_losses,
        candidates=candidates,
    )
