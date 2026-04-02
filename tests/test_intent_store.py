from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from tradeops.app.intent import parse_rebalance_intent
from tradeops.app.models import (
    Account,
    OrderIntent,
    OrderSide,
    Plan,
    PlanTransition,
    PlanType,
    PortfolioState,
    Position,
)
from tradeops.app.store import PlanStore


def test_parse_rebalance_intent_extracts_allocations() -> None:
    intent = parse_rebalance_intent(
        "Rebalance my portfolio today to 80% VOO, 20% NVDA",
        requested_at=datetime(2026, 4, 2, 10, 0, tzinfo=UTC),
    )

    assert intent.target_allocations == {"VOO": Decimal("0.8"), "NVDA": Decimal("0.2")}
    assert intent.requested_date == "today"


def test_plan_store_round_trip(tmp_path) -> None:
    store = PlanStore(database_url=f"sqlite:///{tmp_path / 'tradeops.db'}")
    portfolio = PortfolioState(
        captured_at=datetime(2026, 4, 2, 10, 0, tzinfo=UTC),
        account=Account(
            account_id="acct-1",
            account_number="PA123",
            status="ACTIVE",
            is_paper=True,
            buying_power=Decimal("1000"),
            cash=Decimal("100"),
            equity=Decimal("1100"),
        ),
        positions=[
            Position(
                symbol="VOO",
                qty=Decimal("1"),
                market_value=Decimal("500"),
                cost_basis=Decimal("450"),
                unrealized_pl=Decimal("50"),
                unrealized_plpc=Decimal("0.1111"),
            )
        ],
    )
    intent = parse_rebalance_intent("Rebalance my portfolio today to 80% VOO, 20% NVDA")
    plan = Plan(
        plan_id="rebalance-1",
        plan_type=PlanType.REBALANCE,
        created_at=datetime(2026, 4, 2, 10, 0, tzinfo=UTC),
        transition=PlanTransition(target_allocations={"VOO": Decimal("0.8"), "NVDA": Decimal("0.2")}),
        orders=[
            OrderIntent(
                step_id="step-1",
                symbol="VOO",
                side=OrderSide.BUY,
                notional=Decimal("100"),
                client_order_id_seed="step-1",
            )
        ],
        summary="Rebalance into VOO and NVDA.",
    )

    store.save_plan(plan, portfolio, intent)
    record = store.get_plan("rebalance-1")

    assert record.plan.plan_id == "rebalance-1"
    assert record.intent.target_allocations["NVDA"] == Decimal("0.2")
    assert record.portfolio.account.account_number == "PA123"

    approved = store.approve_plan("rebalance-1")
    assert approved.is_approved is True
