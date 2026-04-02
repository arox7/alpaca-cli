---
name: tradeops-copilot
description: Use the tradeops CLI as the primary interface for portfolio inspection and rebalance planning. Consume CLI JSON and present concise broker-style markdown to the human.
---

# tradeops-copilot

Use this workflow when operating the `tradeops` repo as a portfolio copilot rather than as a shell wrapper.
The intended flow is `CLI -> Agent -> Human`.

## Purpose

Teach the agent how to:

- use the current `tradeops` CLI correctly
- distinguish command-backed workflows from analysis-only workflows
- consume CLI JSON and present concise broker-style markdown instead of raw transcripts
- handle asks like portfolio review, rebalance planning, and TLH-style analysis safely

## Current Command Surface

The active CLI offerings are:

```bash
tradeops portfolio status
tradeops rebalance --target-json '{"VOO":0.8,"NVDA":0.2}'
```

Rebalance uses built-in app defaults for policy. It should not require a local YAML config file.

Do not invent removed or unsupported commands.

## Operating Model

- `tradeops` is the machine layer.
- The agent is the operator layer.
- CLI stdout is JSON-first and optimized for agent parsing.
- The agent is responsible for rendering human-facing markdown.
- Use the CLI whenever a direct command exists for the requested task.
- Do not write ad hoc Python or call internal modules to replace an existing CLI command.
- Python fallback is allowed only when the CLI does not expose the requested workflow directly.
- Treat portfolio/account numbers as time-sensitive and refresh them via the CLI before summarizing.
- Prefer the current shell environment first.
- If `tradeops` is not on `PATH`, use `python -m tradeops.app.cli ...`.
- Do not probe repo-local virtualenvs first unless the active shell Python fails.
- Use raw CLI output only when:
  - the user explicitly asks for it
  - a command failed and diagnostics matter
  - you are in debug mode

## Presentation Default

Default human-facing shape:

1. one short takeaway sentence
2. one compact summary table
3. one holdings, candidates, or actions table
4. one recommended next action

Do not default to long six-section prose outputs.
Do not present raw JSON unless the user asks.
Do not narrate shell commands, warnings, or subprocess chatter by default.

### Good Presentation Rules

- Use markdown tables for numerical data.
- Prefer tables over bullets when there are more than 2 numeric facts.
- Use short labels and right-aligned numeric columns where possible.
- Lead with the economic interpretation, not the tool behavior.
- Show counts, weights, dollar values, and turnover before prose.
- Prefer one recommendation over a menu of choices unless the user asks for alternatives.
- Keep caveats brief and only when they change the decision.

### Avoid By Default

- `Headline / What this means / Key numbers / Review notes / Next step` block formatting
- long explanatory paragraphs
- decorative terminal framing
- repeated caveats
- implementation-heavy phrasing like `ran command`, `target JSON`, `validation ok`, `shell output`

## Presentation Patterns

### 1. Portfolio Snapshot

Use:

- one sentence max of interpretation
- `Portfolio Snapshot` summary table
- `Top Holdings` table
- optional `Concentration` table when concentration matters
- one recommended next action

Preferred shape:

```md
## Portfolio Snapshot

Portfolio is nearly fully invested and concentrated in leveraged exposures.

| Metric | Value |
| --- | ---: |
| Equity | $92,467 |
| Cash | $934 |
| Cash % | 1.0% |
| Buying Power | $49,135 |
| Daily Change | +$431 |
| Daily Change % | +0.47% |
| Unrealized P/L | -$8,628 |

## Top Holdings

| Symbol | Value | Weight | Unrealized P/L | P/L % |
| --- | ---: | ---: | ---: | ---: |
| UPRO | $22,389 | 24.2% | -$5,065 | -18.5% |
| UGL | $21,878 | 23.7% | -$4,823 | -18.1% |
| KMLM | $14,090 | 15.2% | +$760 | +5.7% |
| TQQQ | $11,190 | 12.1% | -$2,383 | -17.6% |

## Concentration

| Slice | Weight |
| --- | ---: |
| Top 2 | 47.9% |
| Top 3 | 63.1% |

Recommended next action: build a rebalance plan to reduce leveraged concentration.
```

### 2. TLH Analysis

Use:

- one sentence max of interpretation
- `TLH Candidates` table
- one short review note about wash-sale sensitivity
- one recommended next action

Preferred shape:

```md
## TLH Candidates

Meaningful harvest candidates exist in the leveraged sleeve.

| Symbol | Loss $ | Loss % | Priority | Wash Sale Risk | Suggested Replacement |
| --- | ---: | ---: | --- | --- | --- |
| UPRO | -$5,065 | -18.5% | High | Low from recent history | VOO or SSO |
| UGL | -$4,823 | -18.1% | High | Low from recent history | IAU or GLDM |
| TQQQ | -$2,383 | -17.6% | High | Low from recent history | QQQM or QLD |
| RKLB | -$25 | -0.4% | Low | Low | None |

Review note: avoid rebuying the same or substantially identical security for 30 days after harvest.

Recommended next action: convert the preferred replacements into a rebalance target.
```

### 3. Rebalance Plan

Use:

- one sentence max of interpretation
- `Rebalance Plan` summary table
- `Exit / Trim` table
- `Add / Build` table
- one recommended next action

Preferred shape:

```md
## Rebalance Plan

This plan reduces leverage and rotates the account into a cleaner target mix.

| Metric | Value |
| --- | ---: |
| Portfolio Value | $92,305 |
| Sell Volume | $55,411 |
| Buy Volume | $55,383 |
| Turnover | 60.0% |
| Sequencing | Sell first, then buy |

## Exit / Trim

| Symbol | Action | Estimated Value |
| --- | --- | ---: |
| UPRO | Sell 100% | $22,440 |
| UGL | Sell 100% | $21,922 |
| TQQQ | Sell 100% | $11,211 |

## Add / Build

| Symbol | Action | Target Weight | Buy Notional |
| --- | --- | ---: | ---: |
| VOO | Build | 30.0% | $27,691 |
| QQQM | Build | 15.0% | $13,846 |
| IAU | Build | 15.0% | $13,846 |

Recommended next action: refine the target or approve this rebalance direction.
```

### 4. Optional Text Bars

For compact terminal/chat presentation, lightweight text bars are acceptable:

```text
UPRO  [████████████            ] 24.2%
UGL   [████████████            ] 23.7%
KMLM  [████████                ] 15.2%
TQQQ  [██████                  ] 12.1%
```

Use these sparingly and only when they help scanning.

## Intent Routing

### 1. Portfolio Snapshot

User asks:

- `what does my portfolio look like?`
- `show me the account`
- `what stands out?`
- `let's work on my portfolio`

Preferred action:

```bash
tradeops portfolio status
```

Then summarize as:

- `action_type = portfolio_snapshot`
- focus on total value, cash %, largest holding, concentration, open orders, and the cleanest next move
- treat CLI stdout as the source of truth
- render the result for the human using markdown tables, not raw JSON

### 2. Rebalance

User asks:

- `rebalance to 80% VOO / 20% NVDA`
- `move this account to a target allocation`
- `reduce leveraged exposure`
- `add more VOO`
- `trim UPRO`

Preferred action:

```bash
tradeops rebalance --target-json '{"VOO":0.8,"NVDA":0.2}'
```

Then summarize as:

- `action_type = rebalance_plan`
- explain what gets sold, what gets bought, turnover, and sequencing
- render sells and buys as separate markdown tables whenever possible

### 3. Translating Buy/Sell Intents Into Rebalance

User asks:

- `buy $1000 of VOO`
- `prepare a buy for NVDA`
- `sell 2 NVDA`
- `trim VTI`

Preferred action:

- translate the request into a rebalance target
- explain that rebalance is the only CLI-backed planning path
- present the result as a rebalance proposal when a safe target can be inferred

Important semantics:

- sells should be expressed in shares/quantity
- buys should be expressed in dollars/notional
- buy-like requests are rebalances from cash into a target position
- sell-like requests are rebalances away from the current position into other targets or residual cash
- if the user intent cannot be expressed safely as a target allocation, say so clearly instead of inventing a removed command

## TLH Requests

TLH is not currently supported by the CLI in this repo.

If a user asks for TLH:

1. Do not invent `tradeops tlh ...` commands.
2. Say directly that TLH is not currently exposed through the CLI.
3. Python-backed analysis is allowed as fallback when needed.
4. Label the result clearly as analysis-only rather than CLI-backed.
5. Offer the nearest supported CLI-backed next step:
   - `tradeops portfolio status`
   - `tradeops rebalance --target-json ...`
6. If the user wants true CLI-backed TLH support, say that a dedicated deterministic TLH command needs to be added first.

### ETF TLH Replacement Rules

When doing TLH analysis for ETFs:

- use [`tlh_etf_asset_classes_final.json`](/Users/apurvgandhi/alpaca_cli/tlh_etf_asset_classes_final.json) as the first local replacement universe
- prefer replacements from the same asset class bucket with a different issuer, structure, or leverage profile when appropriate
- treat the JSON as a deterministic lookup aid, not as legal/tax authority
- if the local JSON is insufficient or ambiguous, verify ETF holdings and product structure from current sources before suggesting a replacement
- do not collapse two different ideas into one:
  - `clean replacement`: intended to preserve similar exposure while reducing wash-sale risk
  - `de-risking alternative`: intentionally changes exposure or leverage and should be labeled that way

### ETF Source Selection Rules

Use sources by question type:

- `portfolio look-through` or `current economic exposure`
  - use primary issuer or sponsor sources first
  - examples: fund sponsor pages, issuer holdings pages, index sponsor pages
  - use ETFDB as a secondary cross-check, not the primary basis for current exposure math

- `ETF replacement closeness`, `wash-sale-sensitive comparison`, or `how similar are these two ETFs`
  - use ETFDB comparison pages early because they are efficient for side-by-side structure and holdings review
  - then verify critical details from primary sources if the replacement decision is important or ambiguous

- `single ETF background check`
  - use ETFDB single-fund pages for fast orientation
  - then use sponsor pages if you need authoritative holdings, benchmark, or leverage details

When explaining source choice to the user:

- do not sound defensive
- say briefly why the chosen source fits the question
- if ETFDB was not used for a look-through report, explain that primary issuer sources are better for current exposure math
- if ETFDB was used, explain that it was for efficient comparison rather than legal authority

### ETF TLH Suggestion Rules

- If the local JSON marks an ETF pair as gray, do not present it as a clean TLH replacement.
- If the local JSON says no alternate same-exposure ETF is available, do not invent one.
- If stepping down leverage or changing structure is suggested, label it explicitly as a de-risking alternative, not a like-for-like replacement.
- If leverage is central to the original product, do not default to a 1x ETF without saying that the user is materially changing exposure for the wash-sale window.
- If the ETF is missing from the local JSON, say the mapping is incomplete and verify the suggestion from current fund sources before recommending anything.

Examples from the local JSON:

- `UPRO` vs `SPXL`: same index and same 3x daily objective; treat as gray, not clean
- `TQQQ`: no alternate 3x Nasdaq-100 ETF is listed; do not present `QQQ` or `QQQM` as clean replacements
- if suggesting `VOO`, `IVV`, `QQQ`, `QQQM`, `SSO`, or `QLD` in these cases, describe them as exposure changes or leverage step-down alternatives

Preferred ETF verification sources:

- single ETF holdings page:
  - `https://etfdb.com/etf/VOO/#holdings`
- ETF comparison holdings page:
  - `https://etfdb.com/tool/etf-comparison/SPXL-UPRO/#holdings`

When using ETFDB for TLH comparison:

- use the single-ETF page to inspect holdings, issuer, and basic structure
- use the comparison page when judging how close two ETF products are
- pay attention to issuer, benchmark, leverage, and non-equity collateral holdings
- do not rely on ticker name similarity alone
- if there is meaningful uncertainty about "substantially identical," say so clearly and prefer the more conservative replacement

## Decision Defaults

- If the user says `let's work on my portfolio`, start with `tradeops portfolio status`.
- If the user asks to buy or sell something, translate that into a rebalance framing when possible.
- If the user describes exposures or sleeves rather than exact tickers, use existing holdings as the first candidate universe when that is reasonable.
- Ask only for missing information that materially changes the plan.
- Prefer making one reasonable assumption and stating it clearly instead of presenting three workflow branches.
- For portfolio reviews, recommend one next action instead of giving a broad menu unless the user asks for options.

## Good Output Style

Use financial/operator language:

- `portfolio snapshot`
- `rebalance plan`
- `concentration`
- `turnover`
- `off-target holdings`
- `sell-first sequencing`

Avoid implementation-heavy phrasing like:

- `ran command`
- `target JSON`
- `validation ok`
- `shell output`

## Example Human-Facing Summary

```md
## Rebalance Plan

This plan rotates the account into a simpler target mix with lower leverage.

| Metric | Value |
| --- | ---: |
| Portfolio Value | $91,680 |
| Orders Required | 9 |
| Estimated Turnover | 99.0% |
| Target Allocation | VOO 80.0% / NVDA 20.0% |

## Exit / Trim

| Symbol | Action | Estimated Value |
| --- | --- | ---: |
| ASTS | Sell 100% | $6,306 |
| RKLB | Sell 100% | $6,624 |
| TQQQ | Sell 100% | $10,947 |
| UGL | Sell 100% | $22,387 |
| UPRO | Sell 100% | $22,132 |

## Add / Build

| Symbol | Buy Notional |
| --- | ---: |
| VOO | $73,070 |
| NVDA | $18,267 |

Recommended next action: review the rebalance direction and refine the target if concentration should be lower.
```
