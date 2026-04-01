from datetime import datetime, UTC
from decimal import Decimal

from tradeops.app.models import (
    OrderIntent,
    OrderSide,
    Plan,
    PlanTransition,
    PlanType,
    ValidationIssue,
)


def test_plan_and_order_models_validate() -> None:
    order = OrderIntent(
        step_id="sell-vti",
        symbol="VTI",
        side=OrderSide.SELL,
        qty=Decimal("10"),
        client_order_id_seed="plan-123-sell-vti",
    )
    plan = Plan(
        plan_id="plan-123",
        plan_type=PlanType.TLH,
        created_at=datetime.now(UTC),
        orders=[order],
        transition=PlanTransition(
            source_symbol="VTI",
            replacement_symbol="SCHB",
        ),
    )

    assert plan.plan_id == "plan-123"
    assert plan.orders[0].symbol == "VTI"
    assert plan.orders[0].type == "market"
    assert plan.transition.replacement_symbol == "SCHB"


def test_plan_validation_issues_are_simple() -> None:
    issue = ValidationIssue(code="paper_only", message="Execution requires a paper account.")
    assert issue.code == "paper_only"
