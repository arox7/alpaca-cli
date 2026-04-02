from __future__ import annotations

import json
from collections.abc import Callable
from decimal import Decimal
from importlib.metadata import PackageNotFoundError, version

import typer
from rich.console import Console

from tradeops.app.alpaca_client import AlpacaClient
from tradeops.app.config import load_app_config
from tradeops.app.models import PortfolioState
from tradeops.app.planner import build_rebalance_plan
from tradeops.app.render import render_plan_review, render_portfolio_status
from tradeops.app.validator import validate_plan


app = typer.Typer(
    help=(
        "Deterministic trade-ops CLI for Alpaca paper trading.\n\n"
        "CLI surface is intentionally minimal: portfolio status and rebalance."
    ),
    epilog=(
        "Examples:\n"
        "  tradeops portfolio status\n"
        "  tradeops rebalance --target-json '{\"VOO\":0.8,\"NVDA\":0.2}'"
    ),
    no_args_is_help=True,
    rich_markup_mode="markdown",
)
portfolio_app = typer.Typer(help="Read-only paper portfolio inspection commands.", no_args_is_help=True)
console = Console()


def _version_callback(value: bool) -> None:
    if not value:
        return
    try:
        resolved = version("tradeops")
    except PackageNotFoundError:
        resolved = "0.1.0"
    console.print(f"tradeops {resolved}")
    raise typer.Exit()


@app.callback()
def cli(
    version: bool = typer.Option(
        False,
        "--version",
        help="Show the installed tradeops version and exit.",
        callback=_version_callback,
        is_eager=True,
    ),
) -> None:
    """TradeOps command group."""


def _format_cli_error(exc: Exception, action: str) -> str:
    message = str(exc).strip()
    if message == "Not Found":
        return (
            f"Alpaca returned 'Not Found' while running {action}. "
            "This usually means your credentials do not match paper trading credentials. "
            "Verify TRADEOPS_ALPACA_API_KEY and TRADEOPS_ALPACA_SECRET_KEY."
        )
    if message:
        return message
    return f"{type(exc).__name__} while running {action}."


def _load_portfolio(fetch_portfolio: Callable[[], PortfolioState] | None = None) -> PortfolioState:
    loader = fetch_portfolio or AlpacaClient().get_portfolio_state
    return loader()


def _parse_target_allocations(target_json: str) -> dict[str, Decimal]:
    payload = json.loads(target_json)
    allocations_payload = payload.get("target_allocations") if isinstance(payload, dict) and "target_allocations" in payload else payload
    if not isinstance(allocations_payload, dict):
        raise ValueError("target JSON must be an object like {\"VOO\":0.8,\"NVDA\":0.2}.")

    allocations: dict[str, Decimal] = {}
    for symbol, weight in allocations_payload.items():
        normalized_symbol = str(symbol).upper()
        allocations[normalized_symbol] = Decimal(str(weight))

    if not allocations:
        raise ValueError("target JSON must include at least one allocation.")
    total_weight = sum(allocations.values())
    if total_weight != Decimal("1"):
        raise ValueError(f"Target allocations must sum to 1.00. Received {total_weight}.")
    return allocations


@portfolio_app.command("status")
def portfolio_status() -> None:
    """Show the current paper account, positions, and recent broker state."""
    try:
        portfolio = _load_portfolio()
    except Exception as exc:
        console.print(f"[red]Error:[/red] {_format_cli_error(exc, 'portfolio status')}")
        raise typer.Exit(code=1) from exc

    render_portfolio_status(console, portfolio)


@app.command("rebalance")
def rebalance(
    target_json: str = typer.Option(..., "--target-json", help="JSON target allocation object."),
) -> None:
    """Build a deterministic rebalance plan from explicit target-allocation JSON."""
    try:
        portfolio = _load_portfolio()
        config = load_app_config()
        target_allocations = _parse_target_allocations(target_json)
        plan = build_rebalance_plan(portfolio, config, target_allocations=target_allocations)
        validation_issues = validate_plan(plan, portfolio, config)
        plan = plan.model_copy(update={"validation_issues": validation_issues})
    except Exception as exc:
        console.print(f"[red]Error:[/red] {_format_cli_error(exc, 'rebalance')}")
        raise typer.Exit(code=1) from exc

    render_plan_review(console, plan)


def main() -> None:
    app()


app.add_typer(portfolio_app, name="portfolio")


if __name__ == "__main__":
    main()
