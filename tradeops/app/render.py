from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from rich.console import Console

from tradeops.app.models import Account, BrokerActivity, BrokerOrder, Plan, PortfolioState, Position


def _fmt_money(value: Decimal | None) -> str:
    if value is None:
        return "-"
    return f"${value:,.2f}"


def _fmt_quantity(value: Decimal | None) -> str:
    if value is None:
        return "-"
    normalized = format(value.normalize(), "f")
    return normalized.rstrip("0").rstrip(".") or "0"


def _fmt_percent(value: Decimal | None) -> str:
    if value is None:
        return "-"
    return f"{value:,.2f}%"


def _fmt_datetime(value: datetime | None) -> str:
    if value is None:
        return "-"
    return value.strftime("%Y-%m-%d %H:%M")


def _markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    header_row = "| " + " | ".join(headers) + " |"
    separator_row = "| " + " | ".join(["---"] * len(headers)) + " |"
    body_rows = ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join([header_row, separator_row, *body_rows])


def _daily_change(account: Account) -> tuple[Decimal | None, Decimal | None]:
    if account.equity is None or account.last_equity is None:
        return None, None
    change = account.equity - account.last_equity
    if account.last_equity == 0:
        return change, None
    return change, (change / account.last_equity) * Decimal("100")

def portfolio_status_markdown(portfolio: PortfolioState) -> str:
    account = portfolio.account
    daily_change, daily_change_pct = _daily_change(account)
    positions = sorted(
        portfolio.positions,
        key=lambda position: position.market_value or Decimal("0"),
        reverse=True,
    )
    positions_rows = [
        [
            position.symbol,
            _fmt_money((position.market_value / position.qty) if position.market_value is not None and position.qty else None),
            _fmt_quantity(position.qty),
            _fmt_money(position.market_value),
            _fmt_money(position.unrealized_pl),
            _fmt_percent((position.unrealized_plpc * Decimal("100")) if position.unrealized_plpc is not None else None),
        ]
        for position in positions
    ] or [["-", "-", "-", "-", "-", "-"]]
    recent_order_rows = [
        [
            order.symbol or "-",
            order.type,
            order.side.value,
            _fmt_quantity(order.qty),
            _fmt_quantity(order.filled_qty),
            _fmt_money(order.avg_fill_price),
            order.status,
            order.source or "-",
            _fmt_datetime(order.created_at),
            _fmt_datetime(order.filled_at),
        ]
        for order in portfolio.recent_orders
    ] or [["-", "-", "-", "-", "-", "-", "-", "-", "-", "-"]]
    activity_rows = [
        [
            activity.activity_type,
            activity.symbol or "-",
            activity.side or "-",
            _fmt_quantity(activity.qty),
            _fmt_datetime(activity.occurred_at),
        ]
        for activity in portfolio.activities[:10]
    ] or [["-", "-", "-", "-", "-"]]

    balances = _markdown_table(
        ["Metric", "Value"],
        [
            ["Account", account.account_number or account.account_id],
            ["Status", account.status],
            ["Paper", "yes" if account.is_paper else "no"],
            ["Equity", _fmt_money(account.equity)],
            ["Buying Power", _fmt_money(account.buying_power)],
            ["Cash", _fmt_money(account.cash)],
            ["Daily Change", _fmt_money(daily_change)],
            ["Daily Change %", _fmt_percent(daily_change_pct)],
            ["Captured At", _fmt_datetime(portfolio.captured_at)],
        ],
    )
    positions_table = _markdown_table(
        ["Asset", "Price", "Qty", "Market Value", "Total P/L ($)", "Total P/L (%)"],
        positions_rows,
    )
    recent_orders = _markdown_table(
        ["Asset", "Type", "Side", "Qty", "Filled", "Avg Fill", "Status", "Source", "Submitted", "Filled At"],
        recent_order_rows,
    )
    recent_activity = _markdown_table(
        ["Type", "Asset", "Side", "Qty", "Occurred At"],
        activity_rows,
    )

    return "\n\n".join(
        [
            f"# Portfolio Summary\n\nBroker View | {'Paper' if account.is_paper else 'Live'} | {account.account_number or account.account_id}",
            "## Account Snapshot\n" + balances,
            "## Positions\n" + positions_table,
            "## Recent Orders\n" + recent_orders,
            "## Recent Activity\n" + recent_activity,
        ]
    )


def render_portfolio_status(console: Console, portfolio: PortfolioState) -> None:
    console.print(portfolio.model_dump_json(indent=2), markup=False, soft_wrap=True)


def render_plan_review(console: Console, plan: Plan) -> None:
    console.print(plan.model_dump_json(indent=2), markup=False, soft_wrap=True)


def plan_review_markdown(plan: Plan) -> str:
    sections = [
        f"# Rebalance Plan\n\nBroker View | {plan.plan_type.value}\n\n"
        + _markdown_table(
            ["Metric", "Value"],
            [
                ["Plan ID", plan.plan_id],
                ["Plan Type", plan.plan_type.value],
                ["Orders", str(len(plan.orders))],
                ["Preflight", "passed" if not plan.validation_issues else f"{len(plan.validation_issues)} issue(s)"],
                ["Summary", plan.summary or "-"],
            ],
        ),
    ]

    if plan.validation_issues:
        sections.append(
            "## Preflight Issues\n"
            + _markdown_table(
                ["Code", "Message"],
                [[issue.code, issue.message] for issue in plan.validation_issues],
            )
        )

    drift_rows = plan.analysis.get("drift_rows")
    if isinstance(drift_rows, list) and drift_rows:
        sections.append(
            "## Rebalance Transition\n"
            + _markdown_table(
                ["Symbol", "Current", "Target", "Trade Delta", "Action"],
                [
                    [
                        str(row.get("symbol", "-")),
                        str(row.get("current_value", "-")),
                        str(row.get("target_value", "-")),
                        str(row.get("trade_delta", "-")),
                        str(row.get("action", "-")),
                    ]
                    for row in drift_rows
                ],
            )
        )

    sections.append(
        "## Order Intents\n"
        + _markdown_table(
            ["Step", "Symbol", "Side", "Qty/Notional", "Depends On"],
            [
                [
                    order.step_id,
                    order.symbol,
                    order.side.value,
                    _fmt_quantity(order.qty) if order.qty is not None else _fmt_money(order.notional),
                    order.depends_on_step_id or "-",
                ]
                for order in plan.orders
            ] or [["-", "-", "-", "-", "-"]],
        )
    )

    return "\n\n".join(sections)
