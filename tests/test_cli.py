from __future__ import annotations

from datetime import datetime, UTC
from decimal import Decimal

from typer.testing import CliRunner

from tradeops.app.cli import app
from tradeops.app.models import Account, PortfolioState, Position


runner = CliRunner()


def _portfolio_state() -> PortfolioState:
    return PortfolioState(
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
    )


def test_portfolio_status_command_renders(monkeypatch) -> None:
    from tradeops.app import cli

    monkeypatch.setattr(cli, "AlpacaClient", lambda: type("StubClient", (), {"get_portfolio_state": _portfolio_state})())

    result = runner.invoke(app, ["portfolio", "status"])

    assert result.exit_code == 0
    assert "Portfolio" in result.stdout
    assert "Positions" in result.stdout
    assert "VTI" in result.stdout


def test_portfolio_status_command_shows_readable_error(monkeypatch) -> None:
    from tradeops.app import cli

    def _raise() -> PortfolioState:
        raise ValueError("Missing required Alpaca credentials: TRADEOPS_ALPACA_API_KEY")

    monkeypatch.setattr(cli, "AlpacaClient", lambda: type("StubClient", (), {"get_portfolio_state": _raise})())

    result = runner.invoke(app, ["portfolio", "status"])

    assert result.exit_code == 1
    assert "Missing required Alpaca credentials" in result.stdout


def test_tlh_scan_command_renders(monkeypatch) -> None:
    from tradeops.app import cli

    monkeypatch.setattr(cli, "AlpacaClient", lambda: type("StubClient", (), {"get_portfolio_state": _portfolio_state})())
    monkeypatch.setattr(
        cli,
        "load_app_config",
        lambda: type(
            "StubConfig",
            (),
            {
                "replacement_map": {"VTI": "SCHB"},
                "wash_sale_lookback_days": 30,
                "tlh_loss_dollar_threshold": Decimal("200"),
                "tlh_loss_percent_threshold": Decimal("5"),
            },
        )(),
    )
    monkeypatch.setattr(
        cli,
        "scan_tlh_candidates",
        lambda portfolio, config: [
            {
                "symbol": "VTI",
                "qty": Decimal("10"),
                "unrealized_loss_dollars": Decimal("250"),
                "unrealized_loss_percent": Decimal("10"),
                "replacement_symbol": "SCHB",
                "wash_sale_warning": "likely_ok",
                "is_candidate": True,
            }
        ],
    )

    result = runner.invoke(app, ["tlh", "scan"])

    assert result.exit_code == 0
    assert "TLH Scan" in result.stdout
    assert "VTI" in result.stdout
    assert "SCHB" in result.stdout
