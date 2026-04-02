from decimal import Decimal

import pytest

from tradeops.app.config import AppSettings, load_app_config, validate_alpaca_settings


def test_app_config_loads_defaults() -> None:
    config = load_app_config()
    assert config.target_allocations == {}
    assert config.drift_threshold_percent == Decimal("5")
    assert config.min_trade_notional == Decimal("100")
    assert config.cash_buffer == Decimal("0")
    assert config.paper_only is True
    assert config.regular_hours_only is True
    assert config.max_order_count == 10
    assert config.allow_partial_fill_continuation is False


def test_validate_alpaca_settings_requires_credentials() -> None:
    settings = AppSettings(alpaca_api_key=None, alpaca_secret_key=None)
    with pytest.raises(ValueError, match="Missing required Alpaca credentials"):
        validate_alpaca_settings(settings)


def test_validate_alpaca_settings_requires_paper_url() -> None:
    settings = AppSettings(
        alpaca_api_key="key",
        alpaca_secret_key="secret",
        alpaca_base_url="https://api.alpaca.markets",
    )
    with pytest.raises(ValueError, match="paper trading"):
        validate_alpaca_settings(settings)


def test_normalized_alpaca_base_url_strips_v2_suffix() -> None:
    settings = AppSettings(
        alpaca_api_key="key",
        alpaca_secret_key="secret",
        alpaca_base_url="https://paper-api.alpaca.markets/v2",
    )
    assert settings.normalized_alpaca_base_url == "https://paper-api.alpaca.markets"
