# tradeops

Deterministic CLI trade-ops copilot for Alpaca paper trading.

`tradeops` is a local-first operator tool for reviewing a paper portfolio and building typed deterministic rebalance plans. It is intentionally narrow: Alpaca paper only, US equities/ETFs only, no autonomous execution, and no free-form model output sent directly to the broker. The CLI is JSON-first and intended to be consumed by an agent, which then presents human-readable summaries.

## Why This Repo Exists

- Review a paper portfolio from the terminal.
- Generate typed rebalance plans before any execution step.
- Keep execution policy deterministic and auditable.
- Support deterministic rebalance workflows without hiding side effects.

## Product Boundaries

- Alpaca paper trading only.
- US equities and ETFs only.
- Regular-hours assumptions for MVP.
- No live trading.
- No options or crypto.
- No autonomous recurring execution.

## Current Command Surface

```bash
tradeops --help
tradeops portfolio status
tradeops rebalance --target-json '{"VOO":0.8,"NVDA":0.2}'
```

## Quickstart

### 1. Requirements

- Python 3.11+
- Alpaca paper trading API key and secret
- macOS/Linux shell or equivalent terminal

### 2. Install

```bash
git clone https://github.com/<your-org-or-user>/alpaca_cli.git
cd alpaca_cli
python3.11 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
```

### 3. Configure

Create `.env` from the example:

```bash
cp .env.example .env
```

Set paper credentials:

```dotenv
TRADEOPS_ALPACA_API_KEY=your_alpaca_paper_api_key
TRADEOPS_ALPACA_SECRET_KEY=your_alpaca_paper_secret_key
TRADEOPS_ALPACA_BASE_URL=https://paper-api.alpaca.markets
TRADEOPS_ALPACA_DATA_FEED=iex
TRADEOPS_DATABASE_URL=sqlite:///tradeops.db
```

### 4. Run

```bash
tradeops portfolio status
tradeops rebalance --target-json '{"VOO":0.8,"NVDA":0.2}'
```

If you see a `Not Found` broker error, your credentials usually do not match the paper environment.

## First 5 Minutes

Inspect the current paper account:

```bash
tradeops portfolio status
```

Generate a rebalance plan from explicit target JSON:

```bash
tradeops rebalance --target-json '{"SPY":0.5,"QQQ":0.5}'
```

Rebalance semantics:

- sell-side adjustments are represented in shares/quantity
- buy-side adjustments are represented in dollars/notional
- a “buy” is modeled as a rebalance from cash into a target position
- a “sell” is modeled as a rebalance away from a current position toward other targets or retained cash

## Configuration

- `.env.example`: environment variables for broker credentials and local paths
- rebalance policy defaults are built into the app; no local policy file is required

## Project Layout

```text
tradeops/
  app/
    cli.py            # Typer command surface
    alpaca_client.py  # read-only Alpaca adapter
    planner.py        # typed plan construction
    validator.py      # execution guardrails
    executor.py       # approval-gated execution flow
    render.py         # terminal and markdown rendering
tests/
runs/
```

## Development

Install dev dependencies:

```bash
pip install -e ".[dev]"
```

Run tests:

```bash
pytest
```

Run a focused subset:

```bash
pytest tests/test_cli.py tests/test_planning.py tests/test_alpaca_client.py
```

## Design Rules

- All broker actions become typed plans first.
- Broker payloads are normalized at the adapter boundary.
- Approval checks belong in the executor, not only in the CLI.
- CLI commands are stdout JSON and optimized for agent consumption.
- Human-facing markdown summaries belong in the agent layer above the CLI.

## Status

The repo already covers:

- shared typed contracts
- read-only Alpaca paper adapter
- deterministic rebalance plan generation
- CLI rendering for operator/LLM consumption

Planned next slices are tracked in [EXECUTION_PLAN.md](EXECUTION_PLAN.md).

## License

MIT. See [LICENSE](LICENSE).
