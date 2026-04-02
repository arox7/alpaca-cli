from __future__ import annotations

from datetime import datetime, UTC
from decimal import Decimal

from rich.console import Console

from tradeops.app.models import Account, BrokerOrder, OrderSide, Plan, PlanTransition, PlanType, PortfolioState, Position, ValidationIssue
from tradeops.app.render import (
    portfolio_status_markdown,
    render_plan_review,
    render_portfolio_status,
)


def test_render_portfolio_status_prints_expected_sections() -> None:
    portfolio = PortfolioState(
        captured_at=datetime.now(UTC),
        account=Account(
            account_id="acct-1",
            account_number="PA123",
            status="ACTIVE",
            is_paper=True,
            buying_power=Decimal("10000"),
            cash=Decimal("2500"),
            equity=Decimal("12500"),
            last_equity=Decimal("13000"),
        ),
        positions=[
            Position(
                symbol="VTI",
                qty=Decimal("10"),
                market_value=Decimal("2500"),
                cost_basis=Decimal("2750"),
                unrealized_pl=Decimal("-250"),
            )
        ],
        open_orders=[
            BrokerOrder(
                order_id="order-1",
                client_order_id="cid-1",
                symbol="SCHB",
                side=OrderSide.BUY,
                qty=Decimal("5"),
                filled_qty=Decimal("5"),
                avg_fill_price=Decimal("250.50"),
                type="market",
                time_in_force="day",
                status="new",
                source="access_key",
            )
        ],
        recent_orders=[
            BrokerOrder(
                order_id="order-1",
                client_order_id="cid-1",
                symbol="SCHB",
                side=OrderSide.BUY,
                qty=Decimal("5"),
                filled_qty=Decimal("5"),
                avg_fill_price=Decimal("250.50"),
                type="market",
                time_in_force="day",
                status="filled",
                source="access_key",
            )
        ],
    )

    console = Console(record=True, width=120)
    render_portfolio_status(console, portfolio)
    output = console.export_text()

    assert '"account_number": "PA123"' in output
    assert '"symbol": "VTI"' in output
    assert '"symbol": "SCHB"' in output
    assert '"equity": "12500"' in output


def test_portfolio_status_markdown_contains_sections() -> None:
    portfolio = PortfolioState(
        captured_at=datetime.now(UTC),
        account=Account(
            account_id="acct-1",
            account_number="PA123",
            status="ACTIVE",
            is_paper=True,
            buying_power=Decimal("10000"),
            cash=Decimal("2500"),
            equity=Decimal("12500"),
            last_equity=Decimal("13000"),
        ),
    )
    output = portfolio_status_markdown(portfolio)

    assert "# Portfolio Summary" in output
    assert "## Account Snapshot" in output


def test_render_plan_review_prints_validation_issues() -> None:
    console = Console(record=True, width=120)
    render_plan_review(
        console,
        Plan(
            plan_id="rebalance-1",
            plan_type=PlanType.REBALANCE,
            created_at=datetime.now(UTC),
            transition=PlanTransition(target_allocations={"VOO": Decimal("0.8"), "NVDA": Decimal("0.2")}),
            validation_issues=[
                ValidationIssue(code="paper_only", message="Execution requires a paper account.")
            ],
            summary="Rebalance plan review.",
        ),
    )
    output = console.export_text()

    assert '"plan_type": "rebalance"' in output
    assert '"code": "paper_only"' in output
    assert '"summary": "Rebalance plan review."' in output
