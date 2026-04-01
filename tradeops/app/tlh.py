from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from tradeops.app.models import AppConfig, PortfolioState, WashSaleWarning


_OPEN_ORDER_STATUSES = {
    "accepted",
    "new",
    "partially_filled",
    "pending_new",
    "pending_replace",
    "pending_cancel",
    "held",
    "done_for_day",
}


def lookup_replacement_symbol(symbol: str, config: AppConfig) -> str | None:
    return config.replacement_map.get(symbol.upper())


def _is_conflicting_order_symbol(symbol: str, open_symbols: set[str], replacement_symbol: str | None) -> bool:
    if symbol in open_symbols:
        return True
    if replacement_symbol and replacement_symbol in open_symbols:
        return True
    return False


def _recent_buy_detected(
    portfolio: PortfolioState,
    symbol: str,
    replacement_symbol: str | None,
    lookback_days: int,
) -> bool:
    lookback_start = portfolio.captured_at - timedelta(days=lookback_days)
    watched_symbols = {symbol}
    if replacement_symbol:
        watched_symbols.add(replacement_symbol)
    for activity in portfolio.activities:
        if activity.side != "buy":
            continue
        if activity.symbol not in watched_symbols:
            continue
        if activity.occurred_at is None:
            continue
        if activity.occurred_at >= lookback_start:
            return True
    return False


def _loss_amount(position_loss: Decimal | None) -> Decimal:
    if position_loss is None or position_loss >= Decimal("0"):
        return Decimal("0")
    return -position_loss


def _loss_percent(loss_percent: Decimal | None) -> Decimal:
    if loss_percent is None or loss_percent >= Decimal("0"):
        return Decimal("0")
    return -(loss_percent * Decimal("100"))


def scan_tlh_candidates(portfolio: PortfolioState, config: AppConfig) -> list[dict[str, object]]:
    open_symbols = {
        order.symbol
        for order in portfolio.open_orders
        if order.status.lower() in _OPEN_ORDER_STATUSES
    }
    rows: list[dict[str, object]] = []

    for position in portfolio.positions:
        symbol = position.symbol.upper()
        replacement_symbol = lookup_replacement_symbol(symbol, config)
        loss_dollars = _loss_amount(position.unrealized_pl)
        loss_percent = _loss_percent(position.unrealized_plpc)
        has_replacement = replacement_symbol is not None
        conflicting_open_orders = _is_conflicting_order_symbol(symbol, open_symbols, replacement_symbol)
        wash_sale_risk = _recent_buy_detected(
            portfolio=portfolio,
            symbol=symbol,
            replacement_symbol=replacement_symbol,
            lookback_days=config.wash_sale_lookback_days,
        )
        candidate = (
            position.qty > 0
            and loss_dollars >= config.tlh_loss_dollar_threshold
            and loss_percent >= config.tlh_loss_percent_threshold
            and has_replacement
            and not conflicting_open_orders
        )
        notes = [
            "Heuristic TLH screen only; does not determine full wash-sale compliance.",
        ]
        if wash_sale_risk:
            notes.append(
                "Recent buy activity detected in lookback window; review before execution."
            )
        if not has_replacement:
            notes.append("No configured replacement symbol.")
        if conflicting_open_orders:
            notes.append("Open order conflict detected on source or replacement symbol.")

        rows.append(
            {
                "symbol": symbol,
                "qty": position.qty,
                "replacement_symbol": replacement_symbol,
                "unrealized_loss_dollars": loss_dollars,
                "unrealized_loss_percent": loss_percent,
                "has_replacement": has_replacement,
                "has_conflicting_open_orders": conflicting_open_orders,
                "wash_sale_warning": (
                    WashSaleWarning.CAUTION if wash_sale_risk else WashSaleWarning.LIKELY_OK
                ).value,
                "is_candidate": candidate,
                "notes": notes,
            }
        )

    return rows
