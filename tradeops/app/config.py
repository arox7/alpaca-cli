from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

from tradeops.app.models import AppConfig


ROOT_DIR = Path(__file__).resolve().parents[2]
CONFIGS_DIR = ROOT_DIR / "configs"
RUNS_DIR = ROOT_DIR / "runs"
REPORTS_DIR = ROOT_DIR / "reports"


class AppSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="TRADEOPS_",
        env_file=(".env", ".env.local"),
        extra="ignore",
    )

    alpaca_api_key: str | None = None
    alpaca_secret_key: str | None = None
    alpaca_base_url: str = "https://paper-api.alpaca.markets"
    alpaca_data_feed: str = "iex"
    database_url: str = f"sqlite:///{ROOT_DIR / 'tradeops.db'}"
    replacement_map_path: Path = Field(default=CONFIGS_DIR / "replacement_map.yaml")
    target_model_path: Path = Field(default=CONFIGS_DIR / "target_model.yaml")

    @property
    def paper_mode(self) -> bool:
        return "paper" in self.alpaca_base_url.lower()


def load_yaml_model(path: Path, model_type):
    data = yaml.safe_load(path.read_text()) or {}
    return model_type.model_validate(data)


def load_replacement_map(path: Path | None = None) -> dict[str, str]:
    settings = AppSettings()
    data = yaml.safe_load((path or settings.replacement_map_path).read_text()) or {}
    replacements = data.get("replacements", [])
    return {
        item["source_symbol"]: item["replacement_symbol"]
        for item in replacements
        if item.get("source_symbol") and item.get("replacement_symbol")
    }


def load_target_model(path: Path | None = None) -> dict:
    settings = AppSettings()
    return yaml.safe_load((path or settings.target_model_path).read_text()) or {}


def load_app_config() -> AppConfig:
    settings = AppSettings()
    target_model = load_target_model(settings.target_model_path)
    allocations = {
        item["symbol"]: item["target_weight"]
        for item in target_model.get("allocations", [])
        if item.get("symbol") is not None and item.get("target_weight") is not None
    }
    return AppConfig(
        replacement_map=load_replacement_map(settings.replacement_map_path),
        target_allocations=allocations,
        drift_threshold_percent=target_model.get("drift_threshold_percent", "5"),
        min_trade_notional=target_model.get("min_trade_notional", "100"),
        cash_buffer=target_model.get("cash_buffer", "0"),
    )


def validate_alpaca_settings(settings: AppSettings | None = None) -> AppSettings:
    resolved = settings or AppSettings()
    missing = []
    if not resolved.alpaca_api_key:
        missing.append("TRADEOPS_ALPACA_API_KEY")
    if not resolved.alpaca_secret_key:
        missing.append("TRADEOPS_ALPACA_SECRET_KEY")
    if missing:
        joined = ", ".join(missing)
        raise ValueError(f"Missing required Alpaca credentials: {joined}")
    if not resolved.paper_mode:
        raise ValueError(
            "TradeOps MVP only supports Alpaca paper trading. "
            f"Configured base URL is {resolved.alpaca_base_url!r}."
        )
    return resolved
