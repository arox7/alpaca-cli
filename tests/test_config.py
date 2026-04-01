import pytest

from tradeops.app.config import AppSettings, load_app_config, load_replacement_map, load_target_model, validate_alpaca_settings


def test_replacement_map_loads() -> None:
    replacement_map = load_replacement_map()
    assert replacement_map["VTI"] == "SCHB"


def test_target_model_loads() -> None:
    target_model = load_target_model()
    assert target_model["allocations"]


def test_app_config_loads() -> None:
    config = load_app_config()
    assert config.replacement_map["IVV"] == "VOO"


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
