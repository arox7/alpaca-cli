from __future__ import annotations

from decimal import Decimal

from rich.box import SIMPLE_HEAVY
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from tradeops.app.models import Account, BrokerOrder, PortfolioState, Position


def _fmt_money(value: Decimal | None) -> str:
    if value is None:
        return "-"
    return f"${value:,.2f}"


def _fmt_quantity(value: Decimal | None) -> str:
    if value is None:
        return "-"
    normalized = format(value.normalize(), "f")
    return normalized.rstrip("0").rstrip(".") or "0"


def render_account_summary(account: Account) -> Panel:
    summary = Table.grid(padding=(0, 2))
    summary.add_row("Account", account.account_number or account.account_id)
    summary.add_row("Status", account.status)
    summary.add_row("Paper", "yes" if account.is_paper else "no")
    summary.add_row("Equity", _fmt_money(account.equity))
    summary.add_row("Cash", _fmt_money(account.cash))
    summary.add_row("Buying Power", _fmt_money(account.buying_power))
    return Panel(summary, title="Portfolio", border_style="cyan")


def render_positions_table(positions: list[Position]) -> Table:
    table = Table(title="Positions", box=SIMPLE_HEAVY)
    table.add_column("Symbol")
    table.add_column("Qty", justify="right")
    table.add_column("Market Value", justify="right")
    table.add_column("Cost Basis", justify="right")
    table.add_column("Unrealized P/L", justify="right")

    if not positions:
        table.add_row("No positions", "-", "-", "-", "-")
        return table

    for position in positions:
        table.add_row(
            position.symbol,
            _fmt_quantity(position.qty),
            _fmt_money(position.market_value),
            _fmt_money(position.cost_basis),
            _fmt_money(position.unrealized_pl),
        )
    return table


def render_open_orders_table(open_orders: list[BrokerOrder]) -> Table:
    table = Table(title="Open Orders", box=SIMPLE_HEAVY)
    table.add_column("Symbol")
    table.add_column("Side")
    table.add_column("Qty", justify="right")
    table.add_column("Type")
    table.add_column("Status")

    if not open_orders:
        table.add_row("No open orders", "-", "-", "-", "-")
        return table

    for order in open_orders:
        table.add_row(
            order.symbol,
            order.side.value,
            _fmt_quantity(order.qty),
            order.type,
            order.status,
        )
    return table


def render_portfolio_status(console: Console, portfolio: PortfolioState) -> None:
    console.print(render_account_summary(portfolio.account))
    console.print(render_positions_table(portfolio.positions))
    console.print(render_open_orders_table(portfolio.open_orders))


def render_tlh_scan(console: Console, rows: list[dict[str, object]]) -> None:
    table = Table(title="TLH Scan", box=SIMPLE_HEAVY)
    table.add_column("Symbol")
    table.add_column("Qty", justify="right")
    table.add_column("Loss $", justify="right")
    table.add_column("Loss %", justify="right")
    table.add_column("Replacement")
    table.add_column("Warning")
    table.add_column("Candidate")

    if not rows:
        table.add_row("No positions", "-", "-", "-", "-", "-", "-")
        console.print(table)
        return

    for row in rows:
        loss_dollars = row.get("unrealized_loss_dollars")
        loss_percent = row.get("unrealized_loss_percent")
        table.add_row(
            str(row.get("symbol", "-")),
            _fmt_quantity(row.get("qty") if isinstance(row.get("qty"), Decimal) else None),
            _fmt_money(loss_dollars if isinstance(loss_dollars, Decimal) else None),
            f"{loss_percent:.2f}%" if isinstance(loss_percent, Decimal) else "-",
            str(row.get("replacement_symbol") or "-"),
            str(row.get("wash_sale_warning") or "-"),
            "yes" if row.get("is_candidate") else "no",
        )

    console.print(table)
