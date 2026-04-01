# tradeops

CLI trade-ops copilot for Alpaca paper trading.

## MVP Focus

- TLH opportunity scanning
- typed rebalance and sell-then-buy plans
- deterministic paper execution with approvals
- local audit logs and markdown reports
- a repeatable Codex demo flow

## Planned Commands

```bash
tradeops portfolio status
tradeops rebalance plan --target configs/target_model.yaml
tradeops tlh scan
tradeops tlh report --month 2026-04
tradeops tlh plan --symbol VTI
tradeops exec run <plan_id>
tradeops runs show <run_id>
tradeops streams watch
```

## Architecture

See [EXECUTION_PLAN.md](/Users/apurvgandhi/alpaca_cli/EXECUTION_PLAN.md) for the track split, file ownership, merge order, and 7-day schedule.

## Repo Status

This repo is currently in planning/scaffolding stage. The next implementation slice is:

1. freeze shared models and config contracts
2. add Alpaca paper account/positions/activity loading
3. implement TLH scan and plan generation
4. render a dry-run CLI review
5. execute one deterministic sell-then-buy paper workflow

## Guardrails

- typed plans first
- paper only
- deterministic execution
- explicit approval before submit
- append-friendly run and audit logging
