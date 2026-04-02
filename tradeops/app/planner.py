from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal, ROUND_DOWN

from tradeops.app.models import (
    AppConfig,
    OrderIntent,
    OrderSide,
    Plan,
    PlanTransition,
    PlanType,
    PortfolioState,
)


def _resolve_created_at(created_at: datetime | None) -> datetime:
    return created_at or datetime.now(UTC)


def _plan_id(prefix: str, created_at: datetime, suffix: str) -> str:
    return f"{prefix}-{suffix.lower()}-{created_at.strftime('%Y%m%d%H%M%S')}"


def _money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"))


def _qty(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.0001"), rounding=ROUND_DOWN)


def _position_market_value(position) -> Decimal | None:
    return position.market_value


def _position_price(position) -> Decimal | None:
    market_value = _position_market_value(position)
    if market_value is None or position.qty <= 0:
        return None
    return market_value / position.qty


def build_rebalance_plan(
    portfolio: PortfolioState,
    config: AppConfig,
    target_allocations: dict[str, Decimal] | None = None,
    created_at: datetime | None = None,
) -> Plan:
    allocations = target_allocations or config.target_allocations
    if not allocations:
        raise ValueError("Target allocations are required for rebalance planning.")
    total_weight = sum(allocations.values())
    if total_weight != Decimal("1"):
        raise ValueError(f"Target allocations must sum to 1.00. Received {total_weight}.")

    created = _resolve_created_at(created_at)
    plan_id = _plan_id("rebalance", created, "portfolio")
    equity = portfolio.account.equity
    if equity is None:
        raise ValueError("Account equity is required for rebalance planning.")
    investable_equity = max(equity - config.cash_buffer, Decimal("0"))

    positions_by_symbol = {position.symbol.upper(): position for position in portfolio.positions}
    sell_orders: list[OrderIntent] = []
    buy_orders: list[OrderIntent] = []
    drift_rows: list[dict[str, str]] = []
    sell_candidates: list[tuple[str, Decimal, Decimal, Decimal]] = []
    buy_candidates: list[tuple[str, Decimal, Decimal, Decimal]] = []
    expected_cash_delta = Decimal("0")

    for symbol, target_weight in allocations.items():
        normalized_symbol = symbol.upper()
        position = positions_by_symbol.get(normalized_symbol)
        current_value = _position_market_value(position) if position is not None else Decimal("0")
        current_value = current_value or Decimal("0")
        target_value = investable_equity * target_weight
        delta = target_value - current_value
        current_weight = (current_value / equity) if equity > 0 else Decimal("0")
        drift_percent = abs(target_weight - current_weight) * Decimal("100")
        if abs(delta) < config.min_trade_notional or drift_percent < config.drift_threshold_percent:
            drift_rows.append(
                {
                    "symbol": normalized_symbol,
                    "current_value": str(_money(current_value)),
                    "target_value": str(_money(target_value)),
                    "trade_delta": str(_money(delta)),
                    "action": "hold",
                }
            )
            continue

        if delta < 0:
            if position is None:
                continue
            price = _position_price(position)
            if price is None or price <= 0:
                continue
            sell_qty = min(position.qty, _qty(abs(delta) / price))
            if sell_qty <= 0:
                continue
            sell_candidates.append((normalized_symbol, sell_qty, current_value, target_value))
            expected_cash_delta += abs(delta)
            drift_rows.append(
                {
                    "symbol": normalized_symbol,
                    "current_value": str(_money(current_value)),
                    "target_value": str(_money(target_value)),
                    "trade_delta": str(_money(delta)),
                    "action": "sell",
                }
            )
            continue

        buy_candidates.append((normalized_symbol, _money(delta), current_value, target_value))
        expected_cash_delta -= delta
        drift_rows.append(
            {
                "symbol": normalized_symbol,
                "current_value": str(_money(current_value)),
                "target_value": str(_money(target_value)),
                "trade_delta": str(_money(delta)),
                "action": "buy",
            }
        )

    for symbol, position in positions_by_symbol.items():
        if symbol in allocations or position.qty <= 0:
            continue
        current_value = _position_market_value(position)
        price = _position_price(position)
        if current_value is None or price is None or price <= 0:
            continue
        if current_value < config.min_trade_notional:
            drift_rows.append(
                {
                    "symbol": symbol,
                    "current_value": str(_money(current_value)),
                    "target_value": str(Decimal("0.00")),
                    "trade_delta": str(_money(-current_value)),
                    "action": "hold",
                }
            )
            continue
        sell_candidates.append((symbol, position.qty, current_value, Decimal("0")))
        expected_cash_delta += current_value
        drift_rows.append(
            {
                "symbol": symbol,
                "current_value": str(_money(current_value)),
                "target_value": str(Decimal("0.00")),
                "trade_delta": str(_money(-current_value)),
                "action": "sell",
            }
        )

    step_index = 1
    for normalized_symbol, sell_qty, _current_value, _target_value in sell_candidates:
        step_id = f"{plan_id}-step-{step_index}"
        step_index += 1
        sell_orders.append(
            OrderIntent(
                step_id=step_id,
                symbol=normalized_symbol,
                side=OrderSide.SELL,
                qty=sell_qty,
                client_order_id_seed=step_id,
                rationale=f"Trim {normalized_symbol} toward target allocation.",
            )
        )

    last_sell_step_id = sell_orders[-1].step_id if sell_orders else None
    for normalized_symbol, buy_notional, _current_value, _target_value in buy_candidates:
        step_id = f"{plan_id}-step-{step_index}"
        step_index += 1
        buy_orders.append(
            OrderIntent(
                step_id=step_id,
                symbol=normalized_symbol,
                side=OrderSide.BUY,
                notional=buy_notional,
                client_order_id_seed=step_id,
                depends_on_step_id=last_sell_step_id,
                rationale=f"Add {normalized_symbol} toward target allocation.",
            )
        )

    return Plan(
        plan_id=plan_id,
        plan_type=PlanType.REBALANCE,
        created_at=created,
        assumptions=[
            "Target allocations are applied to equity net of configured cash buffer.",
            "Buy orders depend on prior sells when sells are present.",
        ],
        orders=[*sell_orders, *buy_orders],
        transition=PlanTransition(
            target_allocations=allocations,
            expected_cash_delta=_money(expected_cash_delta),
            notes=["Deterministic rebalance based on stored portfolio market values."],
        ),
        analysis={
            "equity": str(_money(equity)),
            "investable_equity": str(_money(investable_equity)),
            "cash_buffer": str(_money(config.cash_buffer)),
            "drift_rows": drift_rows,
        },
        summary=(
            f"Move the portfolio toward {len(allocations)} explicit target allocations "
            f"using deterministic sell-first then buy sequencing."
        ),
    )
