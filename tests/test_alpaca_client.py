from __future__ import annotations

import builtins
from datetime import datetime
from decimal import Decimal

import pytest

from tradeops.app.alpaca_client import AlpacaClient
from tradeops.app.config import AppSettings
from tradeops.app.models import OrderSide


class StubAccount:
    id = "acct-1"
    account_number = "PA123"
    status = "ACTIVE"
    buying_power = "10000"
    cash = "2500"
    equity = "12500"
    updated_at = "2026-04-01T09:30:00Z"


class StubPosition:
    def __init__(self, symbol: str, qty: str, market_value: str, cost_basis: str, unrealized_pl: str) -> None:
        self.symbol = symbol
        self.qty = qty
        self.market_value = market_value
        self.cost_basis = cost_basis
        self.unrealized_pl = unrealized_pl
        self.unrealized_plpc = "-0.052"


class StubOrder:
    def __init__(self) -> None:
        self.id = "order-1"
        self.client_order_id = "plan-1-sell-vti"
        self.symbol = "VTI"
        self.side = "sell"
        self.qty = "10"
        self.notional = None
        self.order_type = "market"
        self.time_in_force = "day"
        self.status = "new"
        self.created_at = "2026-04-01T10:00:00Z"


class StubActivity:
    def __init__(self) -> None:
        self.activity_id = "activity-1"
        self.activity_type = "fill"
        self.type = "FILL"
        self.symbol = "VTI"
        self.side = "sell"
        self.qty = "5"
        self.price = "250"
        self.transaction_time = "2026-04-01T10:05:00Z"


class AlternateActivity:
    def __init__(self) -> None:
        self.id = "trade-2"
        self.activity_type_name = "trade_activity"
        self.type = "TRADE_ACTIVITY"
        self.symbol = "SCHB"
        self.side = "BUY"
        self.qty = "3"
        self.price = "22.15"
        self.date = "2026-04-01T11:15:00Z"


class StubTradingClient:
    def get_account(self) -> StubAccount:
        return StubAccount()

    def get_all_positions(self) -> list[StubPosition]:
        return [StubPosition("VTI", "10", "2500", "2750", "-250")]

    def get_orders(self, status: str = "open", limit: int = 100) -> list[StubOrder]:
        assert status == "open"
        assert limit == 100
        return [StubOrder()]

    def get_activities(self) -> list[StubActivity]:
        return [StubActivity()]


class AccountActivitiesOnlyClient(StubTradingClient):
    def get_activities(self) -> list[StubActivity]:
        raise AttributeError("legacy client does not expose get_activities")

    def get_account_activities(self, activity_types=None) -> list[AlternateActivity]:
        assert activity_types is None
        return [AlternateActivity()]


def _settings(**overrides: object) -> AppSettings:
    defaults = {
        "alpaca_api_key": "key",
        "alpaca_secret_key": "secret",
        "alpaca_base_url": "https://paper-api.alpaca.markets",
    }
    defaults.update(overrides)
    return AppSettings(**defaults)


def test_get_account_normalizes_stubbed_account() -> None:
    client = AlpacaClient(settings=_settings(), trading_client=StubTradingClient())

    account = client.get_account()

    assert account.account_id == "acct-1"
    assert account.account_number == "PA123"
    assert account.status == "ACTIVE"
    assert account.is_paper is True
    assert account.buying_power == Decimal("10000")
    assert account.updated_at == datetime.fromisoformat("2026-04-01T09:30:00+00:00")


def test_get_all_positions_normalizes_stubbed_models() -> None:
    client = AlpacaClient(settings=_settings(), trading_client=StubTradingClient())

    positions = client.get_all_positions()

    assert len(positions) == 1
    assert positions[0].symbol == "VTI"
    assert positions[0].qty == Decimal("10")
    assert positions[0].market_value == Decimal("2500")
    assert positions[0].cost_basis == Decimal("2750")
    assert positions[0].unrealized_pl == Decimal("-250")
    assert positions[0].unrealized_plpc == Decimal("-0.052")


def test_get_orders_normalizes_stubbed_models_without_alpaca_imports(monkeypatch: pytest.MonkeyPatch) -> None:
    client = AlpacaClient(settings=_settings(), trading_client=StubTradingClient())

    original_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name.startswith("alpaca."):
            raise ImportError("alpaca-py unavailable in test")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    orders = client.get_orders(status="open")

    assert len(orders) == 1
    assert orders[0].order_id == "order-1"
    assert orders[0].client_order_id == "plan-1-sell-vti"
    assert orders[0].symbol == "VTI"
    assert orders[0].side is OrderSide.SELL
    assert orders[0].qty == Decimal("10")
    assert orders[0].type == "market"
    assert orders[0].time_in_force == "day"
    assert orders[0].status == "new"
    assert orders[0].created_at == datetime.fromisoformat("2026-04-01T10:00:00+00:00")


def test_get_activities_normalizes_primary_activity_method() -> None:
    client = AlpacaClient(settings=_settings(), trading_client=StubTradingClient())

    activities = client.get_activities()

    assert len(activities) == 1
    assert activities[0].activity_id == "activity-1"
    assert activities[0].activity_type == "fill"
    assert activities[0].symbol == "VTI"
    assert activities[0].side == "sell"
    assert activities[0].qty == Decimal("5")
    assert activities[0].price == Decimal("250")
    assert activities[0].raw_type == "fill"
    assert activities[0].occurred_at == datetime.fromisoformat("2026-04-01T10:05:00+00:00")


def test_get_activities_falls_back_to_account_activities_method() -> None:
    client = AlpacaClient(settings=_settings(), trading_client=AccountActivitiesOnlyClient())

    activities = client.get_activities()

    assert len(activities) == 1
    assert activities[0].activity_id == "trade-2"
    assert activities[0].activity_type == "trade_activity"
    assert activities[0].symbol == "SCHB"
    assert activities[0].side == "buy"
    assert activities[0].qty == Decimal("3")
    assert activities[0].price == Decimal("22.15")
    assert activities[0].raw_type == "trade_activity"
    assert activities[0].occurred_at == datetime.fromisoformat("2026-04-01T11:15:00+00:00")


def test_get_portfolio_state_normalizes_stubbed_models() -> None:
    client = AlpacaClient(settings=_settings(), trading_client=StubTradingClient())

    portfolio = client.get_portfolio_state()

    assert portfolio.account.is_paper is True
    assert portfolio.positions[0].symbol == "VTI"
    assert portfolio.positions[0].unrealized_pl == Decimal("-250")
    assert portfolio.open_orders[0].type == "market"
    assert portfolio.activities[0].activity_type == "fill"


def test_client_requires_valid_credentials() -> None:
    with pytest.raises(ValueError, match="Missing required Alpaca credentials"):
        AlpacaClient(settings=AppSettings(alpaca_api_key=None, alpaca_secret_key=None))


def test_client_rejects_non_paper_base_url() -> None:
    with pytest.raises(ValueError, match="paper trading"):
        AlpacaClient(
            settings=_settings(alpaca_base_url="https://api.alpaca.markets"),
            trading_client=StubTradingClient(),
        )
