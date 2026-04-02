# AGENTS.md

## Product

This repo builds a CLI trade-ops copilot for Alpaca paper trading.
The system helps users inspect portfolios and build deterministic rebalance plans safely.

## Scope Rules

- Never submit orders directly from free-form LLM output.
- All actions must become typed plans first.
- Keep MVP limited to Alpaca paper, US equities/ETFs, and regular-hours assumptions.
- Prefer deterministic logic over model decisions.
- Treat TLH analysis as recommendation support, not tax advice.
- Preserve concise CLI output and auditability.

## Current CLI Truth

- Supported CLI commands:
  - `tradeops portfolio status`
  - `tradeops rebalance --target-json ...`
- Unsupported in the current CLI surface:
  - `buy` and `sell` commands
  - `tlh` commands
  - free-form natural-language trade intents from the terminal
  - autonomous execution shortcuts
- Do not invent removed or unsupported commands in responses.
- Prefer the CLI whenever a direct command exists for the requested task.
- Python or internal module calls are allowed only as a fallback when the CLI does not expose the workflow directly.
- Do not bypass an existing CLI command by writing ad hoc Python for the same task.
- If a user asks for TLH, note that TLH is not currently exposed as a CLI command. Python-backed analysis is acceptable only as fallback, and it must be labeled clearly as analysis-only rather than command-backed workflow.
- Rebalance should work from CLI target input plus built-in app defaults. Do not assume a local policy or target YAML file exists.
- `portfolio status` and `rebalance` emit machine-readable JSON to stdout by default.
- The intended flow is `CLI -> Agent -> Human`.

## Engineering Rules

- Keep modules small and composable.
- Use Pydantic models for all external payloads and internal plan contracts.
- Normalize Alpaca SDK payloads at the boundary in `alpaca_client.py`.
- Put execution policy in planners, validators, and executor, not in CLI handlers.
- Generate reports from stored state, not fresh broker calls.
- Enforce approval checks in the executor, not only in the CLI.
- Add tests for planners, validators, executor transitions, and rendering.

## Agent Response Rules

- The CLI is the machine layer. The agent is the operator layer.
- For user requests, use the CLI first whenever the CLI supports the task directly.
- Python snippets, direct module imports, or internal-model inspection are acceptable only when the CLI does not support the requested workflow.
- When using Python as fallback, say clearly that the workflow is analysis-backed rather than CLI-backed.
- Treat portfolio/account values as time-sensitive. For any request involving current numbers, refresh via the relevant CLI command before summarizing.
- Never present prior portfolio values as current unless the user explicitly asks for historical comparison.
- Do not echo raw shell commands, dependency warnings, stack traces, or subprocess chatter by default.
- Prefer typed model inspection and `tradeops.app.operator_summary` over narrating raw CLI tables.
- Treat CLI JSON output as the primary machine contract for supported workflows.
- Do not optimize CLI stdout for direct human reading; optimize it for stable agent parsing.
- After each meaningful action, respond with:
  - headline
  - what this means
  - key numbers
  - action breakdown
  - review notes
  - next step
- Use financial language instead of engineering language:
  - say `rebalance plan`, `concentration`, `turnover`, `off-target holdings`, `sell-first sequencing`
  - avoid phrases like `validation ok`, `ran command`, `target JSON` in user-facing summaries unless the user asks for implementation detail
- The agent, not the CLI, is responsible for rendering human-facing markdown summaries or broker-style tables.
- For `portfolio status`, describe concentration, cash posture, and off-target holdings before recommending the next action.
- CLI commands are stdout-only JSON surfaces for agent consumption, not report publishers.
- For `rebalance`, explain sells, buys, turnover, and sequencing without introducing extra plan classifications unless the user explicitly asks for them.
- For buy-like asks, explain that capital deployment is handled as a rebalance from cash into target weights.
- For sell-like asks, explain that position reduction is handled as a rebalance away from a current holding into other targets or retained cash.
- Only expose raw command output in debug mode or when diagnosing a failure.

## Demo Priorities

- portfolio snapshot
- deterministic rebalance planning
- clean audit log and markdown artifacts

## TLH Handling

- TLH is not currently a first-class CLI command.
- When a user asks for TLH:
  - do not imply the system can execute an end-to-end TLH workflow through the current CLI
  - say clearly that TLH is not currently supported by the CLI
  - Python-backed analysis is allowed as fallback if needed
  - distinguish clearly between CLI-backed actions and analysis-backed suggestions
  - recommend the nearest supported CLI-backed next action:
    - `tradeops portfolio status`
    - `tradeops rebalance --target-json ...`

## Rebalance Semantics

- Rebalance is the only plan-building command in the active CLI surface.
- A buy is represented as a rebalance from cash into one or more target positions.
- A sell is represented as a rebalance away from a current position toward other target positions or retained cash.
- In generated rebalance plans:
  - sells should be expressed in shares/quantity
  - buys should be expressed in dollars/notional
- When translating user intent into `--target-json`, preserve that mental model explicitly.

## Safety Boundaries

- Paper account only for MVP
- No live trading
- No options or crypto
- No autonomous recurring execution
- No hidden side effects during plan generation
