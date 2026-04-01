from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from tradeops.app.config import AppSettings, validate_alpaca_settings
from tradeops.app.models import Account, BrokerActivity, BrokerOrder, OrderSide, PortfolioState, Position


def _as_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    return Decimal(str(value))


def _as_datetime(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).replace("Z", "+00:00")
    return datetime.fromisoformat(text)


def _string_attr(raw: Any, *names: str) -> str | None:
    for name in names:
        value = getattr(raw, name, None)
        if value is not None and value != "":
            return str(value)
    return None


def _activity_timestamp(raw: Any) -> datetime | None:
    return _as_datetime(
        _string_attr(
            raw,
            "transaction_time",
            "activity_time",
            "date",
            "occurred_at",
        )
    )


def _normalize_order_side(value: Any) -> OrderSide:
    side = str(value).lower()
    if side == OrderSide.SELL:
        return OrderSide.SELL
    return OrderSide.BUY


def _normalize_activity_side(value: Any) -> str | None:
    if value is None:
        return None
    side = str(value).lower()
    if side in {"buy", "sell"}:
        return side
    return None


class AlpacaClient:
    """Thin read-only wrapper around alpaca-py's TradingClient for MVP broker state."""

    def __init__(self, settings: AppSettings | None = None, trading_client: Any | None = None) -> None:
        self.settings = validate_alpaca_settings(settings)
        self._trading_client = trading_client

    def _client(self) -> Any:
        if self._trading_client is not None:
            return self._trading_client
        try:
            from alpaca.trading.client import TradingClient
        except ImportError as exc:
            raise RuntimeError(
                "alpaca-py is not installed. Install project dependencies before using broker commands."
            ) from exc

        self._trading_client = TradingClient(
            api_key=self.settings.alpaca_api_key,
            secret_key=self.settings.alpaca_secret_key,
            paper=True,
            url_override=self.settings.alpaca_base_url,
        )
        return self._trading_client

    def _order_filter(self, status: str, limit: int) -> Any:
        try:
            from alpaca.trading.enums import QueryOrderStatus
            from alpaca.trading.requests import GetOrdersRequest
        except ImportError:
            if self._trading_client is None:
                raise RuntimeError(
                    "alpaca-py is not installed. Install project dependencies before using broker commands."
                )
            return None

        return GetOrdersRequest(status=QueryOrderStatus(status), limit=limit)

    def _get_orders_raw(self, status: str, limit: int) -> list[Any]:
        client = self._client()
        request = self._order_filter(status=status, limit=limit)
        if request is not None:
            return client.get_orders(filter=request)

        try:
            return client.get_orders(status=status, limit=limit)
        except TypeError:
            try:
                return client.get_orders(filter={"status": status, "limit": limit})
            except TypeError:
                return client.get_orders()

    def _get_activities_raw(self) -> list[Any]:
        client = self._client()
        for method_name in ("get_activities", "get_account_activities"):
            method = getattr(client, method_name, None)
            if method is None:
                continue
            try:
                result = method()
            except AttributeError:
                continue
            except TypeError:
                result = method(activity_types=None)
            return result or []
        return []

    def get_account(self) -> Account:
        raw = self._client().get_account()
        return Account(
            account_id=str(getattr(raw, "id", "")),
            account_number=getattr(raw, "account_number", None),
            status=str(getattr(raw, "status", "")),
            is_paper=self.settings.paper_mode,
            buying_power=_as_decimal(getattr(raw, "buying_power", None)),
            cash=_as_decimal(getattr(raw, "cash", None)),
            equity=_as_decimal(getattr(raw, "equity", None)),
            updated_at=_as_datetime(getattr(raw, "updated_at", getattr(raw, "created_at", None))),
        )

    def get_all_positions(self) -> list[Position]:
        positions = self._client().get_all_positions()
        return [
            Position(
                symbol=str(getattr(item, "symbol", "")),
                qty=_as_decimal(getattr(item, "qty", None)) or Decimal("0"),
                market_value=_as_decimal(getattr(item, "market_value", None)),
                cost_basis=_as_decimal(getattr(item, "cost_basis", None)),
                unrealized_pl=_as_decimal(getattr(item, "unrealized_pl", None)),
                unrealized_plpc=_as_decimal(getattr(item, "unrealized_plpc", None)),
            )
            for item in positions
        ]

    def get_orders(self, status: str = "open", limit: int = 100) -> list[BrokerOrder]:
        orders = self._get_orders_raw(status=status, limit=limit)
        return [
            BrokerOrder(
                order_id=str(getattr(item, "id", "")),
                client_order_id=getattr(item, "client_order_id", None),
                symbol=str(getattr(item, "symbol", "")),
                side=_normalize_order_side(getattr(item, "side", "")),
                qty=_as_decimal(getattr(item, "qty", None)),
                notional=_as_decimal(getattr(item, "notional", None)),
                type=str(getattr(item, "order_type", getattr(item, "type", "market"))).lower(),
                time_in_force=str(getattr(item, "time_in_force", "day")).lower(),
                status=str(getattr(item, "status", "")),
                created_at=_as_datetime(getattr(item, "created_at", None)),
            )
            for item in orders
        ]

    def get_activities(self) -> list[BrokerActivity]:
        activities: list[BrokerActivity] = []
        for item in self._get_activities_raw():
            raw_type = _string_attr(item, "type", "activity_type")
            activity_type = _string_attr(item, "activity_type", "activity_type_name", "type") or "unknown"
            activities.append(
                BrokerActivity(
                    activity_id=_string_attr(
                        item,
                        "activity_id",
                        "id",
                        "transaction_id",
                        "order_id",
                    )
                    or "",
                    activity_type=activity_type.lower(),
                    symbol=getattr(item, "symbol", None),
                    side=_normalize_activity_side(getattr(item, "side", None)),
                    qty=_as_decimal(getattr(item, "qty", None)),
                    price=_as_decimal(getattr(item, "price", getattr(item, "net_amount", None))),
                    occurred_at=_activity_timestamp(item),
                    raw_type=raw_type.lower() if raw_type is not None else None,
                )
            )
        return activities

    def get_portfolio_state(self) -> PortfolioState:
        return PortfolioState(
            captured_at=datetime.now(timezone.utc),
            account=self.get_account(),
            positions=self.get_all_positions(),
            open_orders=self.get_orders(status="open"),
            activities=self.get_activities(),
        )
