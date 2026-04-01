from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from tradeops.app.models import (
    Account,
    AppConfig,
    BrokerActivity,
    BrokerOrder,
    OrderSide,
    PortfolioState,
    Position,
    Plan,
    PlanTransition,
    PlanType,
    OrderIntent,
)
from tradeops.app.planner import build_rebalance_plan, build_tlh_plan
from tradeops.app.tlh import lookup_replacement_symbol, scan_tlh_candidates
from tradeops.app.validator import validate_plan


@pytest.fixture
def app_config() -> AppConfig:
    return AppConfig(
        replacement_map={"VTI": "SCHB", "IVV": "VOO"},
        target_allocations={
            "VTI": Decimal("0.50"),
            "VXUS": Decimal("0.20"),
            "BND": Decimal("0.30"),
        },
        drift_threshold_percent=Decimal("5"),
        min_trade_notional=Decimal("100"),
        cash_buffer=Decimal("500"),
        max_order_count=2,
        tlh_loss_dollar_threshold=Decimal("200"),
        tlh_loss_percent_threshold=Decimal("5"),
        wash_sale_lookback_days=30,
    )


@pytest.fixture
def portfolio_state() -> PortfolioState:
    captured_at = datetime(2026, 4, 1, 14, 30, tzinfo=UTC)
    return PortfolioState(
        captured_at=captured_at,
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
        ],
        open_orders=[],
        activities=[
            BrokerActivity(
                activity_id="act-1",
                activity_type="FILL",
                symbol="SCHB",
                side="buy",
                qty=Decimal("1"),
                price=Decimal("50"),
                occurred_at=captured_at - timedelta(days=5),
            )
        ],
    )


def test_replacement_lookup_uses_config_map(app_config: AppConfig) -> None:
    assert lookup_replacement_symbol("VTI", app_config) == "SCHB"
    assert lookup_replacement_symbol("MISSING", app_config) is None


def test_tlh_scan_selects_only_eligible_candidates(
    portfolio_state: PortfolioState,
    app_config: AppConfig,
) -> None:
    rows = scan_tlh_candidates(portfolio_state, app_config)

    vti_row = next(row for row in rows if row["symbol"] == "VTI")
    vxus_row = next(row for row in rows if row["symbol"] == "VXUS")

    assert vti_row["is_candidate"] is True
    assert vti_row["replacement_symbol"] == "SCHB"
    assert vti_row["wash_sale_warning"] == "caution"
    assert vxus_row["is_candidate"] is False
    assert vxus_row["has_replacement"] is False


def test_tlh_scan_rejects_conflicting_open_orders(
    portfolio_state: PortfolioState,
    app_config: AppConfig,
) -> None:
    conflicted_state = portfolio_state.model_copy(
        update={
            "open_orders": [
                BrokerOrder(
                    order_id="ord-1",
                    symbol="VTI",
                    side=OrderSide.SELL,
                    qty=Decimal("1"),
                    type="market",
                    time_in_force="day",
                    status="new",
                )
            ]
        }
    )
    rows = scan_tlh_candidates(conflicted_state, app_config)
    vti_row = next(row for row in rows if row["symbol"] == "VTI")
    assert vti_row["is_candidate"] is False
    assert vti_row["has_conflicting_open_orders"] is True


def test_tlh_plan_generation_builds_sell_then_buy(
    portfolio_state: PortfolioState,
    app_config: AppConfig,
) -> None:
    created_at = datetime(2026, 4, 1, 15, 0, tzinfo=UTC)
    plan = build_tlh_plan(portfolio_state, app_config, "VTI", created_at=created_at)

    assert plan.plan_type == PlanType.TLH
    assert len(plan.orders) == 2
    assert plan.orders[0].side == OrderSide.SELL
    assert plan.orders[1].side == OrderSide.BUY
    assert plan.orders[1].depends_on_step_id == plan.orders[0].step_id
    assert plan.transition.source_symbol == "VTI"
    assert plan.transition.replacement_symbol == "SCHB"


def test_rebalance_plan_generation_builds_reviewable_orders(
    portfolio_state: PortfolioState,
    app_config: AppConfig,
) -> None:
    created_at = datetime(2026, 4, 1, 15, 0, tzinfo=UTC)
    plan = build_rebalance_plan(portfolio_state, app_config, created_at=created_at)

    assert plan.plan_type == PlanType.REBALANCE
    assert [order.symbol for order in plan.orders] == ["VXUS", "VTI", "BND"]
    assert plan.orders[0].side == OrderSide.SELL
    assert plan.orders[1].depends_on_step_id == plan.orders[0].step_id
    assert plan.orders[2].depends_on_step_id == plan.orders[0].step_id
    assert plan.transition.target_allocations["VTI"] == Decimal("0.50")


def test_validator_returns_expected_blockers(
    portfolio_state: PortfolioState,
    app_config: AppConfig,
) -> None:
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
        plan_type=PlanType.TLH,
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
        transition=PlanTransition(source_symbol="VTI"),
    )

    issues = validate_plan(invalid_plan, conflicted_state, app_config)
    codes = {issue.code for issue in issues}

    assert "paper_only" in codes
    assert "conflicting_open_orders" in codes
    assert "missing_replacement_symbol" in codes
    assert "max_order_count_exceeded" in codes
    assert "oversized_sell" in codes
    assert "missing_dependency" in codes
    assert "below_min_trade_notional" in codes
