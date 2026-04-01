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
from tradeops.app.tlh import lookup_replacement_symbol


def _resolve_created_at(created_at: datetime | None) -> datetime:
    return created_at or datetime.now(UTC)


def _plan_id(prefix: str, created_at: datetime, suffix: str) -> str:
    return f"{prefix}-{suffix.lower()}-{created_at.strftime('%Y%m%d%H%M%S')}"


def _money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"))


def _qty(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.0001"), rounding=ROUND_DOWN)


def _position_market_value(position) -> Decimal | None:
    if position.market_value is not None:
        return position.market_value
    if position.cost_basis is not None and position.unrealized_pl is not None:
        return position.cost_basis + position.unrealized_pl
    return None


def _position_price(position) -> Decimal | None:
    market_value = _position_market_value(position)
    if market_value is None or position.qty <= 0:
        return None
    return market_value / position.qty


def build_tlh_plan(
    portfolio: PortfolioState,
    config: AppConfig,
    symbol: str,
    created_at: datetime | None = None,
) -> Plan:
    normalized_symbol = symbol.upper()
    position = next((item for item in portfolio.positions if item.symbol.upper() == normalized_symbol), None)
    if position is None:
        raise ValueError(f"No position found for {normalized_symbol}.")
    replacement_symbol = lookup_replacement_symbol(normalized_symbol, config)
    if replacement_symbol is None:
        raise ValueError(f"No replacement symbol configured for {normalized_symbol}.")

    created = _resolve_created_at(created_at)
    plan_id = _plan_id("tlh", created, normalized_symbol)
    sell_step_id = f"{plan_id}-sell"
    buy_step_id = f"{plan_id}-buy"
    replacement_notional = _position_market_value(position)
    buy_order = OrderIntent(
        step_id=buy_step_id,
        symbol=replacement_symbol,
        side=OrderSide.BUY,
        notional=_money(replacement_notional) if replacement_notional is not None else None,
        qty=position.qty if replacement_notional is None else None,
        client_order_id_seed=buy_step_id,
        depends_on_step_id=sell_step_id,
        rationale=f"Buy configured TLH replacement for {normalized_symbol} after sale completes.",
    )
    sell_order = OrderIntent(
        step_id=sell_step_id,
        symbol=normalized_symbol,
        side=OrderSide.SELL,
        qty=position.qty,
        client_order_id_seed=sell_step_id,
        rationale=f"Harvest loss on {normalized_symbol}; review wash-sale risk manually.",
    )

    transition = PlanTransition(
        source_symbol=normalized_symbol,
        replacement_symbol=replacement_symbol,
        expected_cash_delta=Decimal("0.00"),
        notes=[
            "Heuristic TLH plan only; not a complete wash-sale determination.",
            "Buy step depends on sale completion.",
        ],
    )
    analysis = {
        "source_symbol": normalized_symbol,
        "replacement_symbol": replacement_symbol,
        "position_qty": str(position.qty),
        "market_value": str(replacement_notional) if replacement_notional is not None else None,
        "unrealized_pl": str(position.unrealized_pl) if position.unrealized_pl is not None else None,
        "unrealized_plpc": str(position.unrealized_plpc) if position.unrealized_plpc is not None else None,
    }
    return Plan(
        plan_id=plan_id,
        plan_type=PlanType.TLH,
        created_at=created,
        assumptions=[
            "Plan is generated from normalized portfolio state only.",
            "Execution is regular-hours, paper-only, and reviewable before submit.",
        ],
        orders=[sell_order, buy_order],
        transition=transition,
        analysis=analysis,
        summary=f"Sell {normalized_symbol} then buy {replacement_symbol} as a TLH replacement.",
    )


def build_rebalance_plan(
    portfolio: PortfolioState,
    config: AppConfig,
    target_allocations: dict[str, Decimal] | None = None,
    created_at: datetime | None = None,
) -> Plan:
    allocations = target_allocations or config.target_allocations
    if not allocations:
        raise ValueError("Target allocations are required for rebalance planning.")

    created = _resolve_created_at(created_at)
    plan_id = _plan_id("rebalance", created, "portfolio")
    equity = portfolio.account.equity
    if equity is None:
        derived_equity = sum(
            (_position_market_value(position) or Decimal("0")) for position in portfolio.positions
        ) + (portfolio.account.cash or Decimal("0"))
        equity = derived_equity
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
            "drift_rows": drift_rows,
        },
        summary=f"Rebalance toward {len(allocations)} target allocations.",
    )
