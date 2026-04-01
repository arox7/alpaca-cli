# TradeOps MVP Execution Plan

## Goal

Build a CLI trade-ops copilot for Alpaca paper trading that can:

- scan for TLH opportunities
- generate rebalance and sell-then-buy plans
- execute deterministic paper workflows with approval gates and audit logs
- support a strong Codex demo

## Delivery Principle

This system is an execution copilot, not an autonomous trader.

- Free-form model output never submits orders directly.
- All actionable work becomes typed plans first.
- Execution is deterministic, approval-gated, and fully logged.
- MVP is limited to Alpaca paper, US equities/ETFs, and regular-hours assumptions.

## Repo Layout

```text
tradeops/
  app/
    cli.py
    config.py
    models.py
    alpaca_client.py
    planner.py
    tlh.py
    validator.py
    executor.py
    streams.py
    store.py
    render.py
    scheduler.py
configs/
  target_model.yaml
  replacement_map.yaml
runs/
reports/
tests/
AGENTS.md
README.md
EXECUTION_PLAN.md
```

## Shared Contracts

These are the cross-track contracts that need to be frozen first.

### Core models

- `Plan`
- `Run`
- `RunStep`
- `OrderIntent`
- `TLHCandidate`
- `ValidationResult`
- `PortfolioSnapshot`
- `StreamEvent`
- `TargetModel`
- `ReplacementMap`

### Required interfaces

- `scan_tlh(...) -> list[TLHCandidate]`
- `build_tlh_plan(symbol, ...) -> Plan`
- `build_rebalance_plan(...) -> Plan`
- `validate_plan(plan, account_snapshot, positions, open_orders, activities) -> ValidationResult`
- `AlpacaClient.get_account()`
- `AlpacaClient.get_all_positions()`
- `AlpacaClient.get_orders(...)`
- `AlpacaClient.get_activities(...)`
- `AlpacaClient.submit_order(...)`
- `AlpacaClient.replace_order_by_id(...)`
- `AlpacaClient.cancel_order_by_id(...)`
- `TradingStreamAdapter.connect()`
- `TradingStreamAdapter.subscribe_orders()`
- `TradingStreamAdapter.subscribe_account()`
- `RunStore.create_run(...)`
- `RunStore.save_plan(...)`
- `RunStore.save_snapshot(...)`
- `RunStore.append_event(...)`
- `RunStore.update_run_state(...)`
- `Executor.start_run(...)`
- `Executor.handle_event(...)`
- `build_app() -> typer.Typer`
- `write_monthly_tlh_report(month: str) -> Path`

## Parallel Workstreams

Run these four tracks in parallel after the shared contracts are defined.

### Track A: Broker + Execution Foundation

Owner: backend / execution agent

Files:

- `tradeops/app/alpaca_client.py`
- `tradeops/app/streams.py`
- `tradeops/app/executor.py`
- `tradeops/app/store.py`
- `tradeops/app/models.py`
- `tradeops/app/config.py`
- `tests/test_alpaca_client.py`
- `tests/test_store.py`
- `tests/test_streams.py`
- `tests/test_executor.py`

Deliverables:

- Thin Alpaca wrapper normalized into local models
- SQLite-backed plan/run/event persistence
- Trading stream adapter translating websocket events into typed internal events
- Executor state machine with approval gating and dependency sequencing
- One end-to-end canned sell-then-buy paper execution path

Milestones:

1. Normalize Alpaca account, positions, orders, and activities.
2. Create append-friendly SQLite tables for plans, runs, snapshots, orders, and stream events.
3. Translate stream events into typed `StreamEvent` objects.
4. Implement run transitions: `DRAFT`, `VALIDATED`, `AWAITING_APPROVAL`, `SUBMITTING`, `WAITING_FOR_FILL`, `PARTIAL_FILL`, `COMPLETED`, `FAILED`, `ABORTED`.
5. Prove a fixture-backed plan can move from draft to completed.

Dependencies:

- Consumes typed plans from Track B.
- Must expose a single execution surface to Track C.
- Must enforce approval checks internally, not just in CLI.

Risks:

- Paper fills are not live-realistic.
- Stream events may be duplicated or arrive out of order.
- Partial fills can break dependent buy sequencing unless transitions are idempotent.

### Track B: Planning + TLH

Owner: planning / quant agent

Files:

- `tradeops/app/planner.py`
- `tradeops/app/tlh.py`
- `tradeops/app/validator.py`
- `tradeops/app/models.py`
- `tradeops/app/config.py`
- `configs/replacement_map.yaml`
- `configs/target_model.yaml`
- `tests/test_tlh.py`
- `tests/test_planner.py`
- `tests/test_validator.py`

Deliverables:

- TLH candidate scanner
- TLH plan generator
- Rebalance planner
- Validator gates for executable plans
- Curated replacement map and initial target model

Milestones:

1. Define model/config contracts for plans, candidates, targets, and validation results.
2. Implement TLH candidate scoring from positions, activities, and open orders.
3. Implement replacement lookup and wash-sale warning classification.
4. Build typed TLH and rebalance plans without side effects.
5. Validate plans against account state, buying power, order conflicts, and policy rules.

Dependencies:

- Requires normalized broker/account snapshots from Track A.
- Produces typed artifacts consumed directly by Track C.
- Needs demo fixtures from Track D for stable examples.

Risks:

- Wash-sale coverage is heuristic, not complete.
- Replacement map quality directly affects recommendation quality.
- Rebalance math can overtrade without bounded thresholds and cash buffers.

### Track C: CLI + UX + Reports

Owner: DX / UX agent

Files:

- `tradeops/app/cli.py`
- `tradeops/app/render.py`
- `tradeops/app/scheduler.py`
- `tests/test_cli.py`
- `tests/test_render.py`
- `tests/test_reports.py`
- `tests/test_scheduler.py`

Deliverables:

- Typer CLI entrypoint
- Rich terminal rendering for account, candidate, plan, and run views
- Markdown report generation into `reports/`
- Thin local scheduler / task wrapper

Milestones:

1. Register CLI commands for portfolio, TLH, rebalance, execution, runs, and stream watch.
2. Keep handlers thin and delegate business logic to Track A/B modules.
3. Render dry-run plan review before any execution attempt.
4. Generate deterministic monthly TLH and run-summary reports from stored state.
5. Add local scheduler entrypoint for repeatable report workflows.

Dependencies:

- Consumes typed models from Tracks A and B.
- Reads persisted snapshots and runs from Track A.
- Uses demo flow/scripts from Track D.

Risks:

- CLI drift if handlers build ad hoc data instead of typed inputs.
- Reports become non-deterministic if they depend on live broker calls.
- Scheduler scope can expand into unnecessary background infra.

### Track D: Codex Workflow + Repo DX

Owner: tooling / tech-lead agent

Files:

- `AGENTS.md`
- `README.md`
- `scripts/demo_seed.py`
- `scripts/run_demo_flow.py`
- `scripts/generate_reports.py`
- `tests/fixtures/*`
- repo task runner files as needed

Deliverables:

- Repo guardrails for agents
- Quickstart and demo documentation
- Seed fixtures for repeatable paper/demo flows
- Task scripts for test, lint, reports, and demo replay
- Two to three bounded Codex demo tasks

Milestones:

1. Write `AGENTS.md` with product scope and safety constraints.
2. Add README quickstart with exact CLI examples.
3. Create fixture portfolio states with TLH and rebalance scenarios.
4. Add demo scripts that replay the same flow from repo root.
5. Define 2 to 3 small Codex-visible improvements that do not alter execution policy.

Dependencies:

- Needs stable CLI entrypoints from Track C.
- Needs report hooks from Track C and typed plans/runs from A/B.

Risks:

- Demo tasks grow too large and stop being reviewable.
- Docs drift if commands or file names change mid-build.

## Agent Batches

If multiple AI coding agents are available, assign them this way.

### Batch 0: Contract Freeze

Priority: first and blocking

Tasks:

- define `models.py` domain objects
- define `config.py` settings and environment rules
- freeze `Plan`, `OrderIntent`, `TLHCandidate`, `Run`, `ValidationResult`, `StreamEvent`
- define deterministic `client_order_id` format
- decide store schema versioning strategy

Done when:

- all other tracks can code against stable signatures

### Batch 1: Execution Core

Tracks:

- Track A

Parallelism:

- `alpaca_client.py` and `store.py` can start together
- `streams.py` can start once event model is frozen
- `executor.py` starts after `OrderIntent`, `Run`, and store interfaces are stable

### Batch 2: Planning Core

Tracks:

- Track B

Parallelism:

- `tlh.py` and config YAMLs can start together
- `planner.py` starts after plan/order-intent contracts freeze
- `validator.py` starts once account/order snapshot shapes from Track A are stable

### Batch 3: UX Surface

Tracks:

- Track C

Parallelism:

- `cli.py` and `render.py` can start together on placeholder fixtures
- `scheduler.py` and report generation can start once store read APIs are defined

### Batch 4: Demo and Repo Workflow

Tracks:

- Track D

Parallelism:

- `AGENTS.md` and `README.md` can start immediately
- demo fixtures can start once shared models are frozen
- demo scripts can start after core CLI commands exist

## Merge Order

Use this merge order to reduce conflicts.

1. `models.py` + `config.py`
2. `replacement_map.yaml` + `target_model.yaml`
3. `alpaca_client.py` + `store.py`
4. `tlh.py` + `planner.py`
5. `validator.py`
6. `render.py` + `cli.py`
7. `streams.py` + `executor.py`
8. reports + scheduler
9. docs + demo scripts + fixtures

## Seven-Day Execution Grid

### Day 1

- scaffold repo
- freeze models and config contracts
- add `AGENTS.md`
- create fixture shapes and schema versioning plan
- commit replacement map v1

### Day 2

- Track A: account/positions/orders/activities wrappers
- Track B: TLH scanner
- Track C: `portfolio status` and `tlh scan`
- Track D: demo seed portfolio fixtures

### Day 3

- Track A: streams + store
- Track B: TLH plan and rebalance plan
- Track C: plan rendering and report formatting
- Track D: Codex task scripts

### Day 4

- Track A: executor sequencing
- Track B: validator rules
- Track C: approval UX and run summary views
- Track D: demo dry-run friction removal

### Day 5

- integrate planner -> validator -> executor
- fix partial-fill handling
- harden `client_order_id` rules
- run fixture-backed end-to-end tests

### Day 6

- terminal polish
- report polish
- failure-path handling
- fixture cleanup
- quickstart cleanup

### Day 7

- record Codex demo
- run `tradeops tlh scan`
- run `tradeops tlh plan --symbol X`
- show dry-run preview
- execute paper workflow
- show final run log and report

## Definition of Done

The sprint is complete when all five are true.

1. `tradeops portfolio status` shows account and positions.
2. `tradeops tlh scan` returns a deterministic candidate list.
3. `tradeops tlh plan --symbol X` emits a reviewable typed plan.
4. `tradeops exec run <plan_id>` executes in paper with tracked state transitions.
5. The demo can be recorded in one clean take.

## First Implementation Slice

Start with this narrow vertical slice before broadening scope.

1. Define models/config.
2. Load account + positions + activities from Alpaca paper.
3. Run TLH scan on fixture/live paper data.
4. Build one typed TLH plan with one sell and one dependent replacement buy.
5. Validate plan.
6. Render dry-run review in CLI.
7. Execute through state machine in paper.
8. Persist run and emit report.

That slice proves the architecture before adding broader rebalance support.
