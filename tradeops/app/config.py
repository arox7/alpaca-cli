from __future__ import annotations

from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

from tradeops.app.models import AppConfig


ROOT_DIR = Path(__file__).resolve().parents[2]
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

    @property
    def paper_mode(self) -> bool:
        return "paper" in self.alpaca_base_url.lower()

    @property
    def normalized_alpaca_base_url(self) -> str:
        base_url = self.alpaca_base_url.rstrip("/")
        if base_url.endswith("/v2"):
            return base_url[:-3]
        return base_url


def load_app_config() -> AppConfig:
    return AppConfig()


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
