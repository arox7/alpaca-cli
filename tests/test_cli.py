from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

from typer.testing import CliRunner

from tradeops.app.cli import app
from tradeops.app.models import Account, Plan, PlanTransition, PlanType, PortfolioState, Position


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


class StubClient:
    def __init__(self, fn) -> None:
        self._fn = fn

    def get_portfolio_state(self) -> PortfolioState:
        return self._fn()


def test_root_help_shows_only_expected_commands() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "portfolio" in result.stdout
    assert "rebalance" in result.stdout
    assert "buy" not in result.stdout
    assert "sell" not in result.stdout
    assert "tlh" not in result.stdout
    assert "review" not in result.stdout


def test_portfolio_status_command_renders(monkeypatch) -> None:
    from tradeops.app import cli

    monkeypatch.setattr(cli, "AlpacaClient", lambda: StubClient(_portfolio_state))

    result = runner.invoke(app, ["portfolio", "status"])

    assert result.exit_code == 0
    assert '"account_number": "PA123"' in result.stdout
    assert '"symbol": "VTI"' in result.stdout

def test_rebalance_requires_valid_target_json(monkeypatch) -> None:
    from tradeops.app import cli

    monkeypatch.setattr(cli, "AlpacaClient", lambda: StubClient(_portfolio_state))
    monkeypatch.setattr(cli, "load_app_config", lambda: SimpleNamespace())

    result = runner.invoke(app, ["rebalance", "--target-json", "{\"VOO\":0.6,\"QQQ\":0.3}"])

    assert result.exit_code == 1
    assert "sum to 1.00" in result.stdout


def test_rebalance_builds_plan_from_json(monkeypatch) -> None:
    from tradeops.app import cli

    captured: dict[str, object] = {}

    monkeypatch.setattr(cli, "AlpacaClient", lambda: StubClient(_portfolio_state))
    monkeypatch.setattr(cli, "load_app_config", lambda: SimpleNamespace())
    monkeypatch.setattr(cli, "validate_plan", lambda plan, portfolio, config: [])

    def _build(portfolio, config, target_allocations=None):
        captured["targets"] = target_allocations
        return Plan(
            plan_id="rebalance-1",
            plan_type=PlanType.REBALANCE,
            created_at=datetime.now(UTC),
            transition=PlanTransition(target_allocations=target_allocations or {}),
            summary="rebalance plan",
        )

    monkeypatch.setattr(cli, "build_rebalance_plan", _build)

    result = runner.invoke(app, ["rebalance", "--target-json", "{\"VOO\":0.8,\"NVDA\":0.2}"])

    assert result.exit_code == 0
    assert captured["targets"] == {"VOO": Decimal("0.8"), "NVDA": Decimal("0.2")}
    assert '"plan_id": "rebalance-1"' in result.stdout
    assert '"plan_type": "rebalance"' in result.stdout
