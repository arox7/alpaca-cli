# tradeops

Deterministic trade-ops copilot for Alpaca paper trading.

`tradeops` is a narrow CLI for two things:

- inspect a paper portfolio as machine-readable JSON
- build deterministic rebalance plans from explicit target weights

On top of that, this repo includes a daily GitHub Actions workflow that:

- pulls your current paper portfolio
- deterministically finds loss positions and wash-sale watch flags
- sends the structured TLH input plus your policy prompt to an LLM
- emails you a financial-advisor style TLH report

The intended flow is:

```text
tradeops CLI -> agent / workflow -> human decision
```

## Why This Repo Exists

- Keep broker interaction deterministic and auditable.
- Keep the CLI small enough for reliable agent use.
- Separate machine output from human presentation.
- Support daily portfolio review and TLH analysis without autonomous trading.

## Product Boundaries

- Alpaca paper trading only
- US equities and ETFs only
- regular-hours assumptions for MVP
- no live trading
- no options or crypto
- no autonomous recurring execution
- no direct free-form LLM trading

## What You Can Do Today

### Local CLI

- inspect your current paper portfolio
- generate a rebalance plan from explicit target weights

### Scheduled TLH Workflow

- run a daily TLH scan at `3 PM America/New_York`
- apply your own judgment policy from `tlh_prompt.md`
- get an emailed markdown/HTML advisor memo

## Current Command Surface

```bash
tradeops portfolio status
tradeops rebalance --target-json '{"VOO":0.8,"NVDA":0.2}'
```

Notes:

- CLI output is JSON-first for agent consumption.
- Human-facing tables and broker-style summaries belong in the agent or email layer.
- Rebalance is the only plan-building command in the active CLI.

## Quick Start

### Prerequisites

- Python 3.11+
- Alpaca paper API key and secret
- macOS, Linux, or a compatible shell

### Install

```bash
git clone https://github.com/arox7/alpaca-cli.git
cd alpaca-cli
python -m pip install -e ".[dev]"
```

If you prefer a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

### Configure Local Broker Access

Create a local env file:

```bash
cp .env.example .env.local
```

Set your Alpaca paper credentials:

```dotenv
TRADEOPS_ALPACA_API_KEY=your_alpaca_paper_api_key
TRADEOPS_ALPACA_SECRET_KEY=your_alpaca_paper_secret_key
TRADEOPS_ALPACA_BASE_URL=https://paper-api.alpaca.markets
TRADEOPS_ALPACA_DATA_FEED=iex
TRADEOPS_DATABASE_URL=sqlite:///tradeops.db
```

### Sanity Check

```bash
tradeops portfolio status
```

If `tradeops` is not on `PATH`, use:

```bash
python -m tradeops.app.cli portfolio status
```

If you see `Not Found`, your credentials usually do not match the Alpaca paper environment.

## First 5 Minutes

### 1. Inspect the portfolio

```bash
tradeops portfolio status
```

### 2. Build a rebalance plan

```bash
tradeops rebalance --target-json '{"SPY":0.5,"QQQ":0.5}'
```

### 3. Try a more realistic multi-sleeve rebalance

```bash
tradeops rebalance --target-json '{"VOO":0.4,"QQQM":0.2,"IAU":0.2,"KMLM":0.2}'
```

## Rebalance Semantics

This repo intentionally models buying and selling through rebalance, not through standalone order commands.

- sell-side adjustments are represented in shares/quantity
- buy-side adjustments are represented in dollars/notional
- a “buy” is modeled as a rebalance from cash into target positions
- a “sell” is modeled as a rebalance away from a current position into other targets or retained cash
- plans use sell-first then buy sequencing

## Daily TLH GitHub Action

The repo includes:

- workflow: [`.github/workflows/daily-tlh-report.yml`](.github/workflows/daily-tlh-report.yml)
- prompt file: [`tlh_prompt.md`](tlh_prompt.md)
- deterministic TLH extractor: [`tradeops/app/tlh_daily.py`](tradeops/app/tlh_daily.py)
- ETF replacement map: [`tlh_etf_asset_classes_final.json`](tlh_etf_asset_classes_final.json)

### What The Workflow Does

Every day at `3 PM America/New_York`, the workflow:

1. installs the repo
2. runs `tradeops portfolio status`
3. deterministically extracts:
   - all loss positions
   - visible loss dollars and percentages
   - recent-buy wash-sale watch flags
   - local ETF replacement-map context
4. sends that structured input plus your prompt policy to OpenRouter
5. uses `google/gemini-3-flash-preview` by default
6. emails you a markdown/HTML TLH memo
7. uploads the JSON payload and report as GitHub Actions artifacts

### What The LLM Does

The LLM does **not** decide what positions are at a loss.

That part is deterministic.

The LLM is only responsible for:

- deciding which candidates are worth surfacing based on your policy
- choosing how conservative to be in the write-up
- presenting the report in an advisor-style format

Your editable policy lives in [`tlh_prompt.md`](tlh_prompt.md).

### Required GitHub Repository Secrets

Broker:

- `TRADEOPS_ALPACA_API_KEY`
- `TRADEOPS_ALPACA_SECRET_KEY`

LLM:

- `OPENROUTER_API_KEY`

Email:

- `TLH_REPORT_TO_EMAIL`
- `TLH_REPORT_FROM_EMAIL`
- `SMTP_HOST`
- `SMTP_PORT`
- `SMTP_USERNAME`
- `SMTP_PASSWORD`

Recommended Gmail SMTP values:

- `SMTP_HOST = smtp.gmail.com`
- `SMTP_PORT = 587`
- `SMTP_USERNAME = yourgmail@gmail.com`
- `SMTP_PASSWORD = <gmail app password>`
- `TLH_REPORT_FROM_EMAIL = yourgmail@gmail.com`
- `TLH_REPORT_TO_EMAIL = yourgmail@gmail.com`

### Gmail App Password Setup

If you use Gmail for report delivery:

1. enable 2-Step Verification on your Google account
2. create a Google App Password
3. store that app password in `SMTP_PASSWORD`

Do not use your normal Gmail password.

### Trigger It Manually

After merging to `main` and setting secrets:

1. open the repo’s **Actions** tab
2. select **Daily TLH Report**
3. click **Run workflow**

Or use GitHub CLI:

```bash
gh workflow run "Daily TLH Report"
```

### What You Should Expect

- a successful GitHub Actions run
- an uploaded artifact containing:
  - `portfolio.json`
  - `daily_tlh_payload.json`
  - `daily_tlh_report.md`
- an email with both:
  - plain text fallback
  - HTML rendering for cleaner tables

## TLH ETF Replacement Rules

ETF TLH guidance in this repo follows a conservative split between deterministic local mapping and live verification.

Use the local map first:

- [`tlh_etf_asset_classes_final.json`](tlh_etf_asset_classes_final.json)

Important interpretation:

- `clean replacement` means similar exposure with lower wash-sale risk
- `gray replacement` means too close for comfort and should not be treated as clean
- `de-risking alternative` means you are intentionally changing exposure or leverage

Examples:

- `UPRO` vs `SPXL`: gray, not clean
- `TQQQ`: no clean alternate listed in the local map
- stepping down from `UPRO -> VOO` or `TQQQ -> QQQM` is a de-risking choice, not a like-for-like replacement

### When To Use ETFDB

Use ETFDB for the right question:

- ETF comparison / wash-sale-sensitive substitution:
  - example: `https://etfdb.com/tool/etf-comparison/SPXL-UPRO/#holdings`
- single ETF orientation:
  - example: `https://etfdb.com/etf/VOO/#holdings`

For current portfolio look-through or exposure math, prefer issuer/sponsor sources first and use ETFDB as a secondary cross-check.

## Repo Layout

```text
.github/workflows/          # scheduled GitHub Actions workflows
scripts/                    # workflow entry scripts
tradeops/app/
  cli.py                    # Typer command surface
  alpaca_client.py          # read-only Alpaca adapter
  planner.py                # typed rebalance plan construction
  validator.py              # plan guardrails
  executor.py               # approval-gated execution flow
  render.py                 # JSON stdout rendering
  tlh_daily.py              # deterministic daily TLH extraction
tests/                      # focused unit tests
tlh_prompt.md               # editable daily TLH LLM policy
tlh_etf_asset_classes_final.json
```

## Development

Install dev dependencies:

```bash
python -m pip install -e ".[dev]"
```

Run all tests:

```bash
pytest
```

Run focused tests:

```bash
pytest tests/test_cli.py tests/test_alpaca_client.py tests/test_tlh_daily.py tests/test_daily_tlh_report.py
```

## Design Rules

- all broker actions become typed plans first
- broker payloads are normalized at the adapter boundary
- CLI commands are JSON-first and optimized for agent consumption
- human-facing markdown belongs in the agent/report layer
- TLH output is recommendation support, not tax advice
- no hidden side effects during plan generation

## Security Notes

- use Alpaca **paper** credentials only
- use GitHub **repository secrets** for the workflow
- secrets are not public in a public repo, but anyone who can modify workflows is sensitive from a secrets perspective
- prefer a dedicated demo/paper account if you automate daily reporting

## Status

Current repo coverage:

- read-only Alpaca paper adapter
- JSON-first CLI portfolio inspection
- deterministic rebalance planning
- daily hybrid TLH reporting via GitHub Actions

Planned next slices live in [`EXECUTION_PLAN.md`](EXECUTION_PLAN.md).

## License

MIT. See [`LICENSE`](LICENSE).
