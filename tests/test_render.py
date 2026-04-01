from __future__ import annotations

from datetime import datetime, UTC
from decimal import Decimal

from rich.console import Console

from tradeops.app.models import Account, BrokerOrder, OrderSide, PortfolioState, Position
from tradeops.app.render import render_portfolio_status, render_tlh_scan


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
                type="market",
                time_in_force="day",
                status="new",
            )
        ],
    )

    console = Console(record=True, width=120)
    render_portfolio_status(console, portfolio)
    output = console.export_text()

    assert "Portfolio" in output
    assert "Positions" in output
    assert "Open Orders" in output
    assert "VTI" in output
    assert "SCHB" in output


def test_render_tlh_scan_prints_expected_columns() -> None:
    console = Console(record=True, width=120)
    render_tlh_scan(
        console,
        [
            {
                "symbol": "VTI",
                "qty": Decimal("10"),
                "unrealized_loss_dollars": Decimal("250"),
                "unrealized_loss_percent": Decimal("10"),
                "replacement_symbol": "SCHB",
                "wash_sale_warning": "caution",
                "is_candidate": True,
            }
        ],
    )
    output = console.export_text()

    assert "TLH Scan" in output
    assert "Loss $" in output
    assert "VTI" in output
    assert "SCHB" in output
