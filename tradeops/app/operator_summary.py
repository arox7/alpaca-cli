from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field

from tradeops.app.models import AppConfig, OrderIntent, OrderSide, Plan, PlanType, PortfolioState, Position


class SummaryMetric(BaseModel):
    model_config = ConfigDict(frozen=True)

    label: str
    value: str


class OperatorSummary(BaseModel):
    model_config = ConfigDict(frozen=True)

    headline: str
    action_type: str
    what_this_means: str
    key_numbers: list[SummaryMetric] = Field(default_factory=list)
    action_breakdown: list[str] = Field(default_factory=list)
    review_notes: list[str] = Field(default_factory=list)
    next_step: str
    confidence: str

    def render_text(self) -> str:
        lines = [self.headline, "", "What this means", self.what_this_means, "", "Key numbers"]
        lines.extend(f"- {item.label}: {item.value}" for item in self.key_numbers)
        lines.extend(["", "Action breakdown"])
        lines.extend(f"- {item}" for item in self.action_breakdown)
        lines.extend(["", "Review notes"])
        lines.extend(f"- {item}" for item in self.review_notes)
        lines.extend(["", f"Confidence: {self.confidence}", f"Next step: {self.next_step}"])
        return "\n".join(lines)


def _money(value: Decimal | None) -> str:
    if value is None:
        return "-"
    return f"${value:,.2f}"


def _percent(value: Decimal | None) -> str:
    if value is None:
        return "-"
    return f"{value:,.1f}%"


def _portfolio_value(portfolio: PortfolioState) -> Decimal:
    if portfolio.account.equity is not None:
        return portfolio.account.equity
    total = portfolio.account.cash or Decimal("0")
    for position in portfolio.positions:
        if position.market_value is not None:
            total += position.market_value
    return total


def _cash_percent(portfolio: PortfolioState, portfolio_value: Decimal) -> Decimal | None:
    cash = portfolio.account.cash
    if cash is None or portfolio_value <= 0:
        return None
    return (cash / portfolio_value) * Decimal("100")


def _position_price(position: Position) -> Decimal | None:
    if position.market_value is None or position.qty <= 0:
        return None
    return position.market_value / position.qty


def _largest_position(portfolio: PortfolioState, portfolio_value: Decimal) -> tuple[str | None, Decimal | None]:
    ranked = sorted(
        portfolio.positions,
        key=lambda item: item.market_value or Decimal("0"),
        reverse=True,
    )
    if not ranked:
        return None, None
    largest = ranked[0]
    if largest.market_value is None or portfolio_value <= 0:
        return largest.symbol, None
    return largest.symbol, (largest.market_value / portfolio_value) * Decimal("100")


def _off_target_count(portfolio: PortfolioState, config: AppConfig | None) -> int | None:
    if config is None or not config.target_allocations:
        return None
    targets = {symbol.upper() for symbol in config.target_allocations}
    return sum(1 for position in portfolio.positions if position.qty > 0 and position.symbol.upper() not in targets)


def summarize_portfolio_status(
    portfolio: PortfolioState,
    config: AppConfig | None = None,
) -> OperatorSummary:
    portfolio_value = _portfolio_value(portfolio)
    cash_pct = _cash_percent(portfolio, portfolio_value)
    largest_symbol, largest_weight = _largest_position(portfolio, portfolio_value)
    off_target_count = _off_target_count(portfolio, config)

    if largest_weight is not None and largest_weight >= Decimal("25"):
        interpretation = "The portfolio is concentrated in a small number of names and likely needs sells before any major rebalance."
        review_notes = ["Largest holding exceeds 25% of portfolio value.", "Idle cash is limited, so meaningful changes likely require sell-first sequencing."]
    else:
        interpretation = "The portfolio looks fundable for incremental adjustments without a full reset."
        review_notes = ["No single position dominates the portfolio snapshot.", "Cash is available for smaller tactical changes."]

    action_breakdown = [
        "Review current concentration and cash posture.",
        "Generate a rebalance plan if you want the account moved toward an explicit target.",
        "Use rebalance targets to express cash deployment or position reduction.",
    ]
    if off_target_count is not None:
        action_breakdown.insert(1, f"There are {off_target_count} off-target holdings relative to the configured model.")

    key_numbers = [
        SummaryMetric(label="Portfolio value", value=_money(portfolio_value)),
        SummaryMetric(label="Cash", value=f"{_money(portfolio.account.cash)} ({_percent(cash_pct)})"),
        SummaryMetric(label="Open orders", value=str(len(portfolio.open_orders))),
        SummaryMetric(label="Largest holding", value=largest_symbol or "-"),
    ]
    if largest_weight is not None:
        key_numbers.append(SummaryMetric(label="Largest weight", value=_percent(largest_weight)))
    if off_target_count is not None:
        key_numbers.append(SummaryMetric(label="Off-target holdings", value=str(off_target_count)))

    return OperatorSummary(
        headline=f"Pulled a fresh paper portfolio snapshot for {portfolio.account.account_number or portfolio.account.account_id}.",
        action_type="portfolio_snapshot",
        what_this_means=interpretation,
        key_numbers=key_numbers,
        action_breakdown=action_breakdown,
        review_notes=review_notes,
        next_step="Generate a rebalance plan if your goal is to move the portfolio toward a target allocation.",
        confidence="high",
    )


def _sell_notional(order: OrderIntent, portfolio: PortfolioState) -> Decimal:
    if order.qty is None:
        return Decimal("0")
    for position in portfolio.positions:
        if position.symbol.upper() != order.symbol.upper():
            continue
        price = _position_price(position)
        if price is None:
            return Decimal("0")
        return price * order.qty
    return Decimal("0")


def _turnover(plan: Plan, portfolio: PortfolioState) -> Decimal | None:
    portfolio_value = _portfolio_value(portfolio)
    if portfolio_value <= 0:
        return None
    gross = Decimal("0")
    for order in plan.orders:
        if order.side is OrderSide.BUY and order.notional is not None:
            gross += order.notional
        elif order.side is OrderSide.SELL:
            gross += _sell_notional(order, portfolio)
    return (gross / portfolio_value) * Decimal("100")


def _preflight_checks(plan: Plan) -> list[str]:
    if plan.validation_issues:
        return [issue.message for issue in plan.validation_issues]
    checks = [
        "Target weights parsed successfully.",
        "Plan remains paper-only and validation-gated.",
    ]
    dependent_buys = [order for order in plan.orders if order.side is OrderSide.BUY and order.depends_on_step_id]
    if dependent_buys:
        checks.append("Buy steps depend on sells completing.")
    return checks


def _removed_positions(plan: Plan, portfolio: PortfolioState) -> list[str]:
    removals: list[str] = []
    positions_by_symbol = {position.symbol.upper(): position for position in portfolio.positions}
    for order in plan.orders:
        if order.side is not OrderSide.SELL or order.qty is None:
            continue
        position = positions_by_symbol.get(order.symbol.upper())
        if position is None:
            continue
        if order.qty >= position.qty:
            removals.append(order.symbol.upper())
    return sorted(set(removals))

def summarize_rebalance_plan(plan: Plan, portfolio: PortfolioState) -> OperatorSummary:
    targets = plan.transition.target_allocations
    target_text = " / ".join(
        f"{symbol} {_percent(weight * Decimal('100'))}"
        for symbol, weight in targets.items()
    )
    turnover = _turnover(plan, portfolio)
    removed_positions = _removed_positions(plan, portfolio)
    buy_orders = [order for order in plan.orders if order.side is OrderSide.BUY]
    sell_orders = [order for order in plan.orders if order.side is OrderSide.SELL]
    meaning = "This plan sells down positions that are above target and adds capital to positions that are below target using deterministic sell-first then buy sequencing."

    action_breakdown = []
    if removed_positions:
        action_breakdown.append("Sell completely: " + ", ".join(removed_positions))
    if buy_orders:
        action_breakdown.append(
            "Buy: "
            + ", ".join(
                f"{order.symbol} {_money(order.notional)}" for order in buy_orders if order.notional is not None
            )
        )
    if sell_orders and buy_orders:
        action_breakdown.append("Execution sequencing is sell first, then buy.")

    review_notes = []
    if any(symbol.endswith("Q") or symbol.startswith("TQQQ") or symbol.startswith("UPRO") for symbol in removed_positions):
        review_notes.append("The plan reduces leveraged or higher-beta exposure by exiting current off-target holdings.")
    if len(targets) == 1:
        review_notes.append("Post-trade concentration will increase because the target collapses into a single holding.")
    elif len(targets) == 2:
        review_notes.append("Post-trade concentration will still be meaningful because capital is concentrated in only two names.")
    review_notes.extend(_preflight_checks(plan))

    return OperatorSummary(
        headline=f"I prepared a rebalance plan to move the portfolio to {target_text}.",
        action_type="rebalance_plan",
        what_this_means=meaning,
        key_numbers=[
            SummaryMetric(label="Portfolio value", value=_money(_portfolio_value(portfolio))),
            SummaryMetric(label="Orders required", value=str(len(plan.orders))),
            SummaryMetric(label="Estimated turnover", value=_percent(turnover)),
            SummaryMetric(label="Target allocation", value=target_text),
        ],
        action_breakdown=action_breakdown or ["No trade actions were required."],
        review_notes=review_notes,
        next_step="Review the markdown trade memo or execute the plan in paper after operator review.",
        confidence="high" if not plan.validation_issues else "medium",
    )


def _fmt_qty(value: Decimal | None) -> str:
    if value is None:
        return "-"
    normalized = format(value.normalize(), "f")
    return normalized.rstrip("0").rstrip(".") or "0"
