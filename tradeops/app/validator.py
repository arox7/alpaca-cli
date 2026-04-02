from __future__ import annotations

from decimal import Decimal

from tradeops.app.models import AppConfig, Plan, PortfolioState, ValidationIssue


_TERMINAL_STATUSES = {"filled", "canceled", "cancelled", "rejected", "expired"}


def _estimate_order_notional(plan_order, portfolio: PortfolioState) -> Decimal | None:
    if plan_order.notional is not None:
        return plan_order.notional
    if plan_order.qty is None:
        return None
    position = next((item for item in portfolio.positions if item.symbol.upper() == plan_order.symbol.upper()), None)
    if position is None or position.market_value is None or position.qty <= 0:
        return None
    return (position.market_value / position.qty) * plan_order.qty


def validate_plan(plan: Plan, portfolio: PortfolioState, config: AppConfig) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    if config.paper_only and not portfolio.account.is_paper:
        issues.append(
            ValidationIssue(
                code="paper_only",
                message="Execution requires a paper account.",
            )
        )

    if not plan.orders:
        issues.append(
            ValidationIssue(
                code="empty_plan",
                message="Plan has no order intents to review or execute.",
            )
        )

    if len(plan.orders) > config.max_order_count:
        issues.append(
            ValidationIssue(
                code="max_order_count_exceeded",
                message=(
                    f"Plan contains {len(plan.orders)} orders which exceeds the configured maximum "
                    f"of {config.max_order_count}."
                ),
            )
        )

    open_symbols = {
        order.symbol.upper()
        for order in portfolio.open_orders
        if order.status.lower() not in _TERMINAL_STATUSES
    }
    positions_by_symbol = {position.symbol.upper(): position for position in portfolio.positions}
    step_ids = {order.step_id for order in plan.orders}
    available_funds = portfolio.account.buying_power or portfolio.account.cash or Decimal("0")
    projected_sell_proceeds = Decimal("0")
    projected_buy_cost = Decimal("0")

    for order in plan.orders:
        symbol = order.symbol.upper()
        if symbol in open_symbols:
            issues.append(
                ValidationIssue(
                    code="conflicting_open_orders",
                    message=f"Open order conflict exists for {symbol}.",
                )
            )

        if order.depends_on_step_id and order.depends_on_step_id not in step_ids:
            issues.append(
                ValidationIssue(
                    code="missing_dependency",
                    message=f"Order {order.step_id} depends on unknown step {order.depends_on_step_id}.",
                )
            )

        if order.qty is None and order.notional is None:
            issues.append(
                ValidationIssue(
                    code="missing_order_size",
                    message=f"Order {order.step_id} must define qty or notional.",
                )
            )
        if order.qty is not None and order.notional is not None:
            issues.append(
                ValidationIssue(
                    code="ambiguous_order_size",
                    message=f"Order {order.step_id} should not set both qty and notional.",
                )
            )
        if config.regular_hours_only and order.extended_hours:
            issues.append(
                ValidationIssue(
                    code="extended_hours_not_allowed",
                    message=f"Order {order.step_id} enables extended hours in a regular-hours-only policy.",
                )
            )

        estimated_notional = _estimate_order_notional(order, portfolio)
        if estimated_notional is not None and abs(estimated_notional) < config.min_trade_notional:
            issues.append(
                ValidationIssue(
                    code="below_min_trade_notional",
                    message=(
                        f"Order {order.step_id} is below configured minimum trade notional of "
                        f"{config.min_trade_notional}."
                    ),
                )
            )

        if order.side.value == "sell":
            position = positions_by_symbol.get(symbol)
            if position is None:
                issues.append(
                    ValidationIssue(
                        code="missing_position",
                        message=f"Sell order {order.step_id} has no matching position for {symbol}.",
                    )
                )
            elif order.qty is not None and order.qty > position.qty:
                issues.append(
                    ValidationIssue(
                        code="oversized_sell",
                        message=f"Sell order {order.step_id} exceeds available quantity for {symbol}.",
                    )
                )
            if estimated_notional is not None:
                projected_sell_proceeds += estimated_notional
        elif estimated_notional is not None:
            projected_buy_cost += estimated_notional

    if projected_buy_cost > available_funds + projected_sell_proceeds:
        issues.append(
            ValidationIssue(
                code="insufficient_buying_power",
                message=(
                    "Plan buy exposure exceeds available cash/buying power plus projected sell proceeds."
                ),
            )
        )

    return issues
