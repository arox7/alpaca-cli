from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from time import sleep, time

from tradeops.app.alpaca_client import AlpacaClient
from tradeops.app.models import BrokerOrder, OrderIntent, Plan


_TERMINAL_STATUSES = {"filled", "canceled", "cancelled", "rejected", "expired"}


@dataclass(frozen=True)
class ExecutionResult:
    submitted_sell_order_ids: list[str]
    submitted_buy_order_ids: list[str]
    realized_sell_proceeds: Decimal
    resized_buy_notionals: dict[str, Decimal]


def _is_terminal(order: BrokerOrder) -> bool:
    return order.status.lower() in _TERMINAL_STATUSES


def _is_filled(order: BrokerOrder) -> bool:
    return order.status.lower() == "filled"


def _filled_notional(order: BrokerOrder) -> Decimal:
    if order.notional is not None:
        return order.notional
    if order.filled_qty is not None and order.avg_fill_price is not None:
        return order.filled_qty * order.avg_fill_price
    return Decimal("0")


def _wait_for_terminal_order(client: AlpacaClient, order_id: str, timeout_seconds: int, poll_seconds: float) -> BrokerOrder:
    deadline = time() + timeout_seconds
    last_seen: BrokerOrder | None = None
    while time() < deadline:
        last_seen = client.get_order_by_id(order_id)
        if _is_terminal(last_seen):
            return last_seen
        sleep(poll_seconds)
    if last_seen is None:
        raise RuntimeError(f"Timed out waiting for order {order_id}.")
    raise RuntimeError(f"Timed out waiting for terminal status on order {order_id}; last status={last_seen.status}.")


def _split_rebalance_orders(plan: Plan) -> tuple[list[OrderIntent], list[OrderIntent]]:
    sells = [order for order in plan.orders if order.side.value == "sell"]
    buys = [order for order in plan.orders if order.side.value == "buy"]
    return sells, buys


def _buy_notional(order: OrderIntent) -> Decimal:
    if order.notional is not None:
        return order.notional
    raise ValueError(f"Buy order {order.step_id} is missing notional; fill-aware rebalance execution requires notionals.")


def _resize_buy_notionals(buys: list[OrderIntent], realized_sell_proceeds: Decimal) -> dict[str, Decimal]:
    if not buys:
        return {}
    planned_total = sum(_buy_notional(order) for order in buys)
    if planned_total <= 0:
        raise ValueError("Planned buy notional total must be positive.")
    if realized_sell_proceeds <= 0:
        raise RuntimeError("No realized sell proceeds available to fund buy orders.")

    raw_allocations: dict[str, Decimal] = {}
    for order in buys:
        weight = _buy_notional(order) / planned_total
        raw_allocations[order.step_id] = (realized_sell_proceeds * weight).quantize(Decimal("0.01"))

    rounding_gap = realized_sell_proceeds.quantize(Decimal("0.01")) - sum(raw_allocations.values())
    if rounding_gap != 0:
        raw_allocations[buys[-1].step_id] = (raw_allocations[buys[-1].step_id] + rounding_gap).quantize(Decimal("0.01"))
    return raw_allocations


def execute_rebalance_plan_fill_aware(
    plan: Plan,
    client: AlpacaClient,
    timeout_seconds: int = 300,
    poll_seconds: float = 1.0,
) -> ExecutionResult:
    sells, buys = _split_rebalance_orders(plan)
    submitted_sell_order_ids: list[str] = []
    submitted_buy_order_ids: list[str] = []
    filled_sells: list[BrokerOrder] = []

    for order_intent in sells:
        submitted = client.submit_order_intent(order_intent)
        submitted_sell_order_ids.append(submitted.order_id)

    for order_id in submitted_sell_order_ids:
        terminal_order = _wait_for_terminal_order(
            client=client,
            order_id=order_id,
            timeout_seconds=timeout_seconds,
            poll_seconds=poll_seconds,
        )
        if not _is_filled(terminal_order):
            raise RuntimeError(f"Sell order {order_id} did not fill successfully (status={terminal_order.status}).")
        filled_sells.append(terminal_order)

    realized_sell_proceeds = sum(_filled_notional(order) for order in filled_sells).quantize(Decimal("0.01"))
    resized_notionals = _resize_buy_notionals(buys, realized_sell_proceeds)

    for order_intent in buys:
        notional = resized_notionals[order_intent.step_id]
        submitted = client.submit_order_intent(
            order_intent.model_copy(update={"notional": notional, "qty": None})
        )
        submitted_buy_order_ids.append(submitted.order_id)

    return ExecutionResult(
        submitted_sell_order_ids=submitted_sell_order_ids,
        submitted_buy_order_ids=submitted_buy_order_ids,
        realized_sell_proceeds=realized_sell_proceeds,
        resized_buy_notionals=resized_notionals,
    )
