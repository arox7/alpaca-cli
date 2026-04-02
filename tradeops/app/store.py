from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from tradeops.app.config import AppSettings
from tradeops.app.models import Plan, PortfolioState, RebalanceIntent


@dataclass(frozen=True)
class StoredPlanRecord:
    plan: Plan
    portfolio: PortfolioState
    intent: RebalanceIntent
    approved_at: str | None = None

    @property
    def is_approved(self) -> bool:
        return self.approved_at is not None


def _sqlite_path(database_url: str) -> Path:
    prefix = "sqlite:///"
    if not database_url.startswith(prefix):
        raise ValueError("TradeOps store currently supports sqlite:/// paths only.")
    return Path(database_url[len(prefix) :]).expanduser()


class PlanStore:
    def __init__(self, database_url: str | None = None) -> None:
        settings = AppSettings()
        self.database_url = database_url or settings.database_url
        self.db_path = _sqlite_path(self.database_url)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.db_path)
        connection.row_factory = sqlite3.Row
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS plans (
                    plan_id TEXT PRIMARY KEY,
                    plan_type TEXT NOT NULL,
                    intent_json TEXT NOT NULL,
                    plan_json TEXT NOT NULL,
                    portfolio_json TEXT NOT NULL,
                    approved_at TEXT
                )
                """
            )
            connection.commit()

    def save_plan(self, plan: Plan, portfolio: PortfolioState, intent: RebalanceIntent) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO plans (
                    plan_id,
                    plan_type,
                    intent_json,
                    plan_json,
                    portfolio_json,
                    approved_at
                ) VALUES (?, ?, ?, ?, ?, COALESCE((SELECT approved_at FROM plans WHERE plan_id = ?), NULL))
                """,
                (
                    plan.plan_id,
                    plan.plan_type.value,
                    intent.model_dump_json(),
                    plan.model_dump_json(),
                    portfolio.model_dump_json(),
                    plan.plan_id,
                ),
            )
            connection.commit()

    def get_plan(self, plan_id: str) -> StoredPlanRecord:
        with self._connect() as connection:
            row = connection.execute(
                """
                SELECT intent_json, plan_json, portfolio_json, approved_at
                FROM plans
                WHERE plan_id = ?
                """,
                (plan_id,),
            ).fetchone()
        if row is None:
            raise ValueError(f"No stored plan found for {plan_id}.")
        return StoredPlanRecord(
            intent=RebalanceIntent.model_validate_json(row["intent_json"]),
            plan=Plan.model_validate_json(row["plan_json"]),
            portfolio=PortfolioState.model_validate_json(row["portfolio_json"]),
            approved_at=row["approved_at"],
        )

    def approve_plan(self, plan_id: str) -> StoredPlanRecord:
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE plans
                SET approved_at = datetime('now')
                WHERE plan_id = ?
                """,
                (plan_id,),
            )
            connection.commit()
        if cursor.rowcount == 0:
            raise ValueError(f"No stored plan found for {plan_id}.")
        return self.get_plan(plan_id)
