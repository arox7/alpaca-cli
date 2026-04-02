from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from tradeops.app.models import (
    Account,
    AppConfig,
    OrderIntent,
    OrderSide,
    Plan,
    PlanTransition,
    PlanType,
    PortfolioState,
    Position,
)
from tradeops.app.operator_summary import summarize_portfolio_status, summarize_rebalance_plan


def _portfolio_state() -> PortfolioState:
    return PortfolioState(
        captured_at=datetime(2026, 4, 2, 9, 30, tzinfo=UTC),
        account=Account(
            account_id="acct-1",
            account_number="PA123",
            status="ACTIVE",
            is_paper=True,
            cash=Decimal("1000"),
            equity=Decimal("10000"),
            buying_power=Decimal("12000"),
        ),
        positions=[
            Position(
                symbol="UPRO",
                qty=Decimal("10"),
                market_value=Decimal("4000"),
                cost_basis=Decimal("4500"),
                unrealized_pl=Decimal("-500"),
                unrealized_plpc=Decimal("-0.1111"),
            ),
            Position(
                symbol="GLD",
                qty=Decimal("10"),
                market_value=Decimal("2000"),
                cost_basis=Decimal("1900"),
                unrealized_pl=Decimal("100"),
                unrealized_plpc=Decimal("0.0526"),
            ),
            Position(
                symbol="TLT",
                qty=Decimal("20"),
                market_value=Decimal("3000"),
                cost_basis=Decimal("3200"),
                unrealized_pl=Decimal("-200"),
                unrealized_plpc=Decimal("-0.0625"),
            ),
        ],
    )


def _app_config() -> AppConfig:
    return AppConfig(
        target_allocations={"VOO": Decimal("0.80"), "NVDA": Decimal("0.20")},
        drift_threshold_percent=Decimal("5"),
        min_trade_notional=Decimal("100"),
        cash_buffer=Decimal("0"),
        paper_only=True,
        regular_hours_only=True,
        max_order_count=10,
        allow_partial_fill_continuation=False,
    )


def test_portfolio_summary_uses_operator_language() -> None:
    summary = summarize_portfolio_status(_portfolio_state(), _app_config())

    assert summary.action_type == "portfolio_snapshot"
    assert "paper portfolio snapshot" in summary.headline.lower()
    assert any(item.label == "Off-target holdings" and item.value == "3" for item in summary.key_numbers)
    assert "concentrated" in summary.what_this_means.lower()
    assert "rebalance plan" in summary.next_step.lower()


def test_rebalance_summary_uses_generic_plan_label() -> None:
    portfolio = _portfolio_state()
    plan = Plan(
        plan_id="rebalance-1",
        plan_type=PlanType.REBALANCE,
        created_at=datetime(2026, 4, 2, 9, 35, tzinfo=UTC),
        orders=[
            OrderIntent(step_id="1", symbol="UPRO", side=OrderSide.SELL, qty=Decimal("10"), client_order_id_seed="1"),
            OrderIntent(step_id="2", symbol="GLD", side=OrderSide.SELL, qty=Decimal("10"), client_order_id_seed="2"),
            OrderIntent(step_id="3", symbol="TLT", side=OrderSide.SELL, qty=Decimal("20"), client_order_id_seed="3"),
            OrderIntent(step_id="4", symbol="VOO", side=OrderSide.BUY, notional=Decimal("8000"), client_order_id_seed="4", depends_on_step_id="3"),
            OrderIntent(step_id="5", symbol="NVDA", side=OrderSide.BUY, notional=Decimal("2000"), client_order_id_seed="5", depends_on_step_id="3"),
        ],
        transition=PlanTransition(target_allocations={"VOO": Decimal("0.8"), "NVDA": Decimal("0.2")}),
        summary="rebalance plan",
    )

    summary = summarize_rebalance_plan(plan, portfolio)

    assert summary.action_type == "rebalance_plan"
    assert "sell-first then buy sequencing" in summary.what_this_means.lower()
    assert any("Sell completely" in item for item in summary.action_breakdown)
    assert any(metric.label == "Estimated turnover" for metric in summary.key_numbers)
