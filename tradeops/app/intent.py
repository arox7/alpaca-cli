from __future__ import annotations

import re
from datetime import UTC, datetime
from decimal import Decimal

from tradeops.app.models import RebalanceIntent


_REBALANCE_PREFIX = re.compile(r"^\s*rebalance\b", re.IGNORECASE)
_TARGET_SPLIT = re.compile(r"\bto\b", re.IGNORECASE)
_ALLOCATION = re.compile(r"(?P<weight>\d+(?:\.\d+)?)\s*%\s*(?P<symbol>[A-Za-z.]+)")


def parse_rebalance_intent(source_text: str, requested_at: datetime | None = None) -> RebalanceIntent:
    if not _REBALANCE_PREFIX.search(source_text):
        raise ValueError("Only deterministic rebalance intents are supported in the plan compiler right now.")

    parts = _TARGET_SPLIT.split(source_text, maxsplit=1)
    if len(parts) != 2:
        raise ValueError("Rebalance request must include target allocations after 'to'.")

    allocation_matches = list(_ALLOCATION.finditer(parts[1]))
    if not allocation_matches:
        raise ValueError("Rebalance request must include target weights like '80% VOO, 20% NVDA'.")

    allocations: dict[str, Decimal] = {}
    total_weight = Decimal("0")
    for match in allocation_matches:
        weight = Decimal(match.group("weight"))
        symbol = match.group("symbol").upper()
        if symbol in allocations:
            raise ValueError(f"Duplicate target allocation for {symbol}.")
        fraction = weight / Decimal("100")
        allocations[symbol] = fraction
        total_weight += fraction

    if total_weight != Decimal("1"):
        raise ValueError(f"Target allocations must sum to 100%. Parsed {total_weight * Decimal('100')}%.")

    requested_date = "today" if re.search(r"\btoday\b", source_text, re.IGNORECASE) else None
    return RebalanceIntent(
        source_text=source_text.strip(),
        requested_at=requested_at or datetime.now(UTC),
        target_allocations=allocations,
        requested_date=requested_date,
    )
