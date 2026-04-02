from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

from tradeops.app.models import Account, BrokerActivity, BrokerOrder, OrderSide, PortfolioState, Position
from tradeops.app.tlh_daily import build_daily_tlh_input, load_tlh_etf_map


def _portfolio(as_of: datetime) -> PortfolioState:
    return PortfolioState(
        captured_at=as_of,
        account=Account(
            account_id="acct-1",
            account_number="PA123",
            status="ACTIVE",
            is_paper=True,
            equity=Decimal("100000"),
            cash=Decimal("1000"),
        ),
        positions=[
            Position(
                symbol="UPRO",
                qty=Decimal("10"),
                market_value=Decimal("20000"),
                unrealized_pl=Decimal("-5000"),
                unrealized_plpc=Decimal("-0.20"),
            ),
            Position(
                symbol="TQQQ",
                qty=Decimal("10"),
                market_value=Decimal("12000"),
                unrealized_pl=Decimal("-2400"),
                unrealized_plpc=Decimal("-0.15"),
            ),
            Position(
                symbol="UGL",
                qty=Decimal("10"),
                market_value=Decimal("5000"),
                unrealized_pl=Decimal("-1000"),
                unrealized_plpc=Decimal("-0.10"),
            ),
            Position(
                symbol="LUNR",
                qty=Decimal("10"),
                market_value=Decimal("8000"),
                unrealized_pl=Decimal("2000"),
                unrealized_plpc=Decimal("0.25"),
            ),
        ],
        recent_orders=[
            BrokerOrder(
                order_id="order-1",
                symbol="UPRO",
                side=OrderSide.BUY,
                qty=Decimal("1"),
                type="market",
                time_in_force="day",
                status="filled",
                created_at=as_of - timedelta(days=5),
                filled_at=as_of - timedelta(days=5),
            )
        ],
        activities=[
            BrokerActivity(
                activity_id="activity-1",
                activity_type="fill",
                symbol="TQQQ",
                side="buy",
                qty=Decimal("1"),
                occurred_at=as_of - timedelta(days=10),
            )
        ],
    )


def test_load_tlh_etf_map_reads_local_json() -> None:
    etf_map = load_tlh_etf_map(Path("tlh_etf_asset_classes_final.json"))
    assert "asset_classes" in etf_map


def test_build_daily_tlh_input_extracts_loss_candidates_and_replacement_statuses() -> None:
    as_of = datetime(2026, 4, 2, 15, 0, tzinfo=UTC)
    portfolio = _portfolio(as_of)
    etf_map = load_tlh_etf_map(Path("tlh_etf_asset_classes_final.json"))

    digest = build_daily_tlh_input(portfolio, etf_map, as_of=as_of)

    assert digest.candidate_count == 3
    assert digest.total_visible_losses == Decimal("8400")

    by_symbol = {candidate.symbol: candidate for candidate in digest.candidates}

    assert by_symbol["UPRO"].replacement_status == "gray"
    assert [option.ticker for option in by_symbol["UPRO"].replacement_options] == ["SPXL"]
    assert by_symbol["UPRO"].wash_sale_watch is True

    assert by_symbol["TQQQ"].replacement_status == "none"
    assert by_symbol["TQQQ"].replacement_options == []
    assert by_symbol["TQQQ"].wash_sale_watch is True

    assert by_symbol["UGL"].replacement_status == "unmapped"
    assert by_symbol["UGL"].wash_sale_watch is False
