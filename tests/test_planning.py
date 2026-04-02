from datetime import UTC, datetime
from decimal import Decimal

from tradeops.app.models import (
    Account,
    AppConfig,
    BrokerOrder,
    OrderIntent,
    OrderSide,
    Plan,
    PlanTransition,
    PlanType,
    PortfolioState,
    Position,
)
from tradeops.app.planner import build_rebalance_plan
from tradeops.app.validator import validate_plan


def _app_config() -> AppConfig:
    return AppConfig(
        target_allocations={
            "VTI": Decimal("0.50"),
            "VXUS": Decimal("0.20"),
            "BND": Decimal("0.30"),
        },
        drift_threshold_percent=Decimal("5"),
        min_trade_notional=Decimal("100"),
        cash_buffer=Decimal("500"),
        paper_only=True,
        regular_hours_only=True,
        max_order_count=2,
        allow_partial_fill_continuation=False,
    )


def _portfolio_state() -> PortfolioState:
    return PortfolioState(
        captured_at=datetime(2026, 4, 1, 14, 30, tzinfo=UTC),
        account=Account(
            account_id="acct-1",
            account_number="PA123",
            status="ACTIVE",
            is_paper=True,
            cash=Decimal("2000"),
            equity=Decimal("10000"),
            buying_power=Decimal("12000"),
        ),
        positions=[
            Position(
                symbol="VTI",
                qty=Decimal("10"),
                market_value=Decimal("1800"),
                cost_basis=Decimal("2400"),
                unrealized_pl=Decimal("-600"),
                unrealized_plpc=Decimal("-0.25"),
            ),
            Position(
                symbol="VXUS",
                qty=Decimal("10"),
                market_value=Decimal("2500"),
                cost_basis=Decimal("2300"),
                unrealized_pl=Decimal("200"),
                unrealized_plpc=Decimal("0.086956"),
            ),
            Position(
                symbol="BND",
                qty=Decimal("50"),
                market_value=Decimal("2000"),
                cost_basis=Decimal("1900"),
                unrealized_pl=Decimal("100"),
                unrealized_plpc=Decimal("0.052631"),
            ),
            Position(
                symbol="XLK",
                qty=Decimal("4"),
                market_value=Decimal("800"),
                cost_basis=Decimal("700"),
                unrealized_pl=Decimal("100"),
                unrealized_plpc=Decimal("0.142857"),
            ),
        ],
        open_orders=[],
    )


def test_rebalance_plan_generation_builds_reviewable_orders() -> None:
    plan = build_rebalance_plan(_portfolio_state(), _app_config(), created_at=datetime(2026, 4, 1, 15, 0, tzinfo=UTC))

    assert plan.plan_type == PlanType.REBALANCE
    assert [order.symbol for order in plan.orders] == ["VXUS", "XLK", "VTI", "BND"]
    assert plan.orders[0].side == OrderSide.SELL
    assert plan.orders[1].side == OrderSide.SELL
    assert plan.orders[2].depends_on_step_id == plan.orders[1].step_id
    assert plan.orders[3].depends_on_step_id == plan.orders[1].step_id
    assert plan.transition.target_allocations["VTI"] == Decimal("0.50")


def test_validator_returns_expected_blockers() -> None:
    app_config = _app_config()
    portfolio_state = _portfolio_state()
    conflicted_state = portfolio_state.model_copy(
        update={
            "account": portfolio_state.account.model_copy(update={"is_paper": False}),
            "open_orders": [
                BrokerOrder(
                    order_id="ord-2",
                    symbol="VTI",
                    side=OrderSide.SELL,
                    qty=Decimal("1"),
                    type="market",
                    time_in_force="day",
                    status="accepted",
                )
            ],
        }
    )
    invalid_plan = Plan(
        plan_id="plan-1",
        plan_type=PlanType.TRADE,
        created_at=datetime(2026, 4, 1, 15, 0, tzinfo=UTC),
        orders=[
            OrderIntent(
                step_id="sell-vti",
                symbol="VTI",
                side=OrderSide.SELL,
                qty=Decimal("11"),
                client_order_id_seed="sell-vti",
            ),
            OrderIntent(
                step_id="buy-voo",
                symbol="VOO",
                side=OrderSide.BUY,
                notional=Decimal("50"),
                client_order_id_seed="buy-voo",
                depends_on_step_id="missing-step",
            ),
            OrderIntent(
                step_id="buy-schb",
                symbol="SCHB",
                side=OrderSide.BUY,
                notional=Decimal("75"),
                client_order_id_seed="buy-schb",
            ),
        ],
        transition=PlanTransition(),
    )

    issues = validate_plan(invalid_plan, conflicted_state, app_config)
    codes = {issue.code for issue in issues}

    assert "paper_only" in codes
    assert "conflicting_open_orders" in codes
    assert "max_order_count_exceeded" in codes
    assert "oversized_sell" in codes
    assert "missing_dependency" in codes
    assert "below_min_trade_notional" in codes


def test_validator_blocks_insufficient_buying_power() -> None:
    app_config = _app_config()
    portfolio_state = _portfolio_state()
    constrained_state = portfolio_state.model_copy(
        update={
            "account": portfolio_state.account.model_copy(
                update={"buying_power": Decimal("100"), "cash": Decimal("100")}
            )
        }
    )
    plan = Plan(
        plan_id="plan-buy-heavy",
        plan_type=PlanType.REBALANCE,
        created_at=datetime(2026, 4, 1, 15, 0, tzinfo=UTC),
        orders=[
            OrderIntent(
                step_id="buy-vxus",
                symbol="VXUS",
                side=OrderSide.BUY,
                notional=Decimal("500"),
                client_order_id_seed="buy-vxus",
            )
        ],
        transition=PlanTransition(target_allocations={"VXUS": Decimal("1.0")}),
    )

    issues = validate_plan(plan, constrained_state, app_config)
    codes = {issue.code for issue in issues}

    assert "insufficient_buying_power" in codes
