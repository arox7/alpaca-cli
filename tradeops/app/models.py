from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class PlanType(StrEnum):
    TLH = "tlh"
    REBALANCE = "rebalance"
    SELL_THEN_BUY = "sell_then_buy"


class OrderSide(StrEnum):
    BUY = "buy"
    SELL = "sell"


class WashSaleWarning(StrEnum):
    LIKELY_OK = "likely_ok"
    CAUTION = "caution"
    BLOCKED = "blocked"


class Account(BaseModel):
    model_config = ConfigDict(frozen=True)

    account_id: str
    account_number: str | None = None
    status: str
    is_paper: bool
    buying_power: Decimal | None = None
    cash: Decimal | None = None
    equity: Decimal | None = None
    updated_at: datetime | None = None


class Position(BaseModel):
    model_config = ConfigDict(frozen=True)

    symbol: str
    qty: Decimal
    market_value: Decimal | None = None
    cost_basis: Decimal | None = None
    unrealized_pl: Decimal | None = None
    unrealized_plpc: Decimal | None = None


class BrokerOrder(BaseModel):
    model_config = ConfigDict(frozen=True)

    order_id: str
    client_order_id: str | None = None
    symbol: str
    side: OrderSide
    qty: Decimal | None = None
    notional: Decimal | None = None
    type: str
    time_in_force: str
    status: str
    created_at: datetime | None = None


class BrokerActivity(BaseModel):
    model_config = ConfigDict(frozen=True)

    activity_id: str
    activity_type: str
    symbol: str | None = None
    side: Literal["buy", "sell"] | None = None
    qty: Decimal | None = None
    price: Decimal | None = None
    occurred_at: datetime | None = None
    raw_type: str | None = None


class PortfolioState(BaseModel):
    model_config = ConfigDict(frozen=True)

    captured_at: datetime
    account: Account
    positions: list[Position] = Field(default_factory=list)
    open_orders: list[BrokerOrder] = Field(default_factory=list)
    activities: list[BrokerActivity] = Field(default_factory=list)


class OrderIntent(BaseModel):
    model_config = ConfigDict(frozen=True)

    step_id: str
    symbol: str
    side: OrderSide
    qty: Decimal | None = None
    notional: Decimal | None = None
    type: str = "market"
    time_in_force: str = "day"
    extended_hours: bool = False
    client_order_id_seed: str
    limit_price: Decimal | None = None
    depends_on_step_id: str | None = None
    rationale: str | None = None


class ValidationIssue(BaseModel):
    model_config = ConfigDict(frozen=True)

    code: str
    message: str


class PlanTransition(BaseModel):
    model_config = ConfigDict(frozen=True)

    source_symbol: str | None = None
    replacement_symbol: str | None = None
    target_allocations: dict[str, Decimal] = Field(default_factory=dict)
    expected_cash_delta: Decimal | None = None
    notes: list[str] = Field(default_factory=list)


class Plan(BaseModel):
    model_config = ConfigDict(frozen=True)

    plan_id: str
    plan_type: PlanType
    created_at: datetime
    assumptions: list[str] = Field(default_factory=list)
    orders: list[OrderIntent] = Field(default_factory=list)
    transition: PlanTransition = Field(default_factory=PlanTransition)
    analysis: dict[str, Any] = Field(default_factory=dict)
    validation_issues: list[ValidationIssue] = Field(default_factory=list)
    summary: str | None = None


class Run(BaseModel):
    model_config = ConfigDict(frozen=True)

    run_id: str
    plan_id: str
    status: str
    created_at: datetime
    updated_at: datetime
    approval_granted: bool = False
    broker_order_ids: list[str] = Field(default_factory=list)
    failure_reason: str | None = None


class AppConfig(BaseModel):
    model_config = ConfigDict(frozen=True)

    replacement_map: dict[str, str] = Field(default_factory=dict)
    target_allocations: dict[str, Decimal] = Field(default_factory=dict)
    drift_threshold_percent: Decimal = Decimal("5")
    min_trade_notional: Decimal = Decimal("100")
    cash_buffer: Decimal = Decimal("0")
    paper_only: bool = True
    regular_hours_only: bool = True
    max_order_count: int = 10
    allow_partial_fill_continuation: bool = False
    tlh_loss_dollar_threshold: Decimal = Decimal("200")
    tlh_loss_percent_threshold: Decimal = Decimal("5")
    wash_sale_lookback_days: int = 30
