from __future__ import annotations

from collections.abc import Callable

import typer
from rich.console import Console

from tradeops.app.alpaca_client import AlpacaClient
from tradeops.app.config import load_app_config
from tradeops.app.models import PortfolioState
from tradeops.app.render import render_portfolio_status, render_tlh_scan
from tradeops.app.tlh import scan_tlh_candidates


app = typer.Typer(help="TradeOps CLI for Alpaca paper trading.")
portfolio_app = typer.Typer(help="Portfolio inspection commands.")
tlh_app = typer.Typer(help="Tax-loss harvesting commands.")
console = Console()


@app.callback()
def cli() -> None:
    """TradeOps command group."""


def _format_cli_error(exc: Exception) -> str:
    message = str(exc).strip()
    if message:
        return message
    return f"{type(exc).__name__} while loading portfolio status."


def _portfolio_status(fetch_portfolio: Callable[[], PortfolioState] | None = None) -> None:
    try:
        loader = fetch_portfolio or AlpacaClient().get_portfolio_state
        portfolio = loader()
    except Exception as exc:
        console.print(f"[red]Error:[/red] {_format_cli_error(exc)}")
        raise typer.Exit(code=1) from exc

    render_portfolio_status(console, portfolio)


@portfolio_app.command("status")
def portfolio_status() -> None:
    """Show paper account, positions, and open orders."""
    _portfolio_status()


@tlh_app.command("scan")
def tlh_scan() -> None:
    """Scan the current paper portfolio for TLH opportunities."""
    try:
        client = AlpacaClient()
        portfolio = client.get_portfolio_state()
        config = load_app_config()
        rows = scan_tlh_candidates(portfolio, config)
    except Exception as exc:
        console.print(f"[red]Error:[/red] {_format_cli_error(exc)}")
        raise typer.Exit(code=1) from exc

    render_tlh_scan(console, rows)


def main() -> None:
    app()


app.add_typer(portfolio_app, name="portfolio")
app.add_typer(tlh_app, name="tlh")
