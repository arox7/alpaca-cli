from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from tradeops.app.executor import execute_rebalance_plan_fill_aware
from tradeops.app.models import BrokerOrder, OrderIntent, OrderSide, Plan, PlanTransition, PlanType


class StubExecutionClient:
    def __init__(self) -> None:
        self.orders_by_id: dict[str, BrokerOrder] = {}
        self.submitted_intents: list[OrderIntent] = []
        self._counter = 0

    def submit_order_intent(self, intent: OrderIntent) -> BrokerOrder:
        self.submitted_intents.append(intent)
        self._counter += 1
        order_id = f"order-{self._counter}"
        if intent.side is OrderSide.SELL:
            status = "filled"
            filled_qty = intent.qty
            avg_fill_price = Decimal("100")
            notional = None
        else:
            status = "new"
            filled_qty = Decimal("0")
            avg_fill_price = None
            notional = intent.notional
        order = BrokerOrder(
            order_id=order_id,
            client_order_id=intent.client_order_id_seed,
            symbol=intent.symbol,
            side=intent.side,
            qty=intent.qty,
            filled_qty=filled_qty,
            notional=notional,
            avg_fill_price=avg_fill_price,
            type=intent.type,
            time_in_force=intent.time_in_force,
            status=status,
            created_at=datetime.now(UTC),
        )
        self.orders_by_id[order_id] = order
        return order

    def get_order_by_id(self, order_id: str) -> BrokerOrder:
        return self.orders_by_id[order_id]


def test_execute_rebalance_plan_resizes_buys_from_realized_sells() -> None:
    plan = Plan(
        plan_id="rebalance-1",
        plan_type=PlanType.REBALANCE,
        created_at=datetime.now(UTC),
        orders=[
            OrderIntent(
                step_id="sell-1",
                symbol="AAA",
                side=OrderSide.SELL,
                qty=Decimal("1"),
                client_order_id_seed="sell-1",
            ),
            OrderIntent(
                step_id="sell-2",
                symbol="BBB",
                side=OrderSide.SELL,
                qty=Decimal("2"),
                client_order_id_seed="sell-2",
            ),
            OrderIntent(
                step_id="buy-1",
                symbol="VOO",
                side=OrderSide.BUY,
                notional=Decimal("800"),
                client_order_id_seed="buy-1",
                depends_on_step_id="sell-2",
            ),
            OrderIntent(
                step_id="buy-2",
                symbol="NVDA",
                side=OrderSide.BUY,
                notional=Decimal("200"),
                client_order_id_seed="buy-2",
                depends_on_step_id="sell-2",
            ),
        ],
        transition=PlanTransition(target_allocations={"VOO": Decimal("0.8"), "NVDA": Decimal("0.2")}),
    )
    client = StubExecutionClient()

    result = execute_rebalance_plan_fill_aware(plan, client=client, timeout_seconds=3, poll_seconds=0.01)

    assert result.realized_sell_proceeds == Decimal("300.00")
    assert result.resized_buy_notionals == {
        "buy-1": Decimal("240.00"),
        "buy-2": Decimal("60.00"),
    }
    submitted_buy_intents = [item for item in client.submitted_intents if item.side is OrderSide.BUY]
    assert submitted_buy_intents[0].notional == Decimal("240.00")
    assert submitted_buy_intents[1].notional == Decimal("60.00")


def test_execute_rebalance_plan_raises_when_sell_not_filled() -> None:
    plan = Plan(
        plan_id="rebalance-2",
        plan_type=PlanType.REBALANCE,
        created_at=datetime.now(UTC),
        orders=[
            OrderIntent(
                step_id="sell-1",
                symbol="AAA",
                side=OrderSide.SELL,
                qty=Decimal("1"),
                client_order_id_seed="sell-1",
            ),
            OrderIntent(
                step_id="buy-1",
                symbol="VOO",
                side=OrderSide.BUY,
                notional=Decimal("100"),
                client_order_id_seed="buy-1",
                depends_on_step_id="sell-1",
            ),
        ],
        transition=PlanTransition(target_allocations={"VOO": Decimal("1.0")}),
    )
    client = StubExecutionClient()

    def _submit_with_reject(intent: OrderIntent) -> BrokerOrder:
        order = StubExecutionClient.submit_order_intent(client, intent)
        if intent.side is OrderSide.SELL:
            client.orders_by_id[order.order_id] = order.model_copy(update={"status": "rejected"})
        return client.orders_by_id[order.order_id]

    client.submit_order_intent = _submit_with_reject  # type: ignore[assignment]

    with pytest.raises(RuntimeError, match="did not fill successfully"):
        execute_rebalance_plan_fill_aware(plan, client=client, timeout_seconds=2, poll_seconds=0.01)
