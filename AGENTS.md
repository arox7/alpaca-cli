# AGENTS.md

## Product

This repo builds a CLI trade-ops copilot for Alpaca paper trading.
The system helps users plan TLH, rebalance portfolios, and execute sell-then-buy workflows safely.

## Scope Rules

- Never submit orders directly from free-form LLM output.
- All actions must become typed plans first.
- Keep MVP limited to Alpaca paper, US equities/ETFs, and regular-hours assumptions.
- Prefer deterministic logic over model decisions.
- Treat TLH output as recommendation support, not tax advice.
- Preserve concise CLI output and auditability.

## Engineering Rules

- Keep modules small and composable.
- Use Pydantic models for all external payloads and internal plan contracts.
- Normalize Alpaca SDK payloads at the boundary in `alpaca_client.py`.
- Put execution policy in planners, validators, and executor, not in CLI handlers.
- Generate reports from stored state, not fresh broker calls.
- Enforce approval checks in the executor, not only in the CLI.
- Add tests for planners, validators, executor transitions, and rendering.

## Demo Priorities

- TLH scan
- TLH plan
- sell-then-buy execution
- clean audit log

## Safety Boundaries

- Paper account only for MVP
- No live trading
- No options or crypto
- No autonomous recurring execution
- No hidden side effects during plan generation
