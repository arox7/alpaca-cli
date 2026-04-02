from __future__ import annotations

import argparse
import json
import os
import smtplib
import sys
import urllib.error
import urllib.request
from datetime import datetime
from email.message import EmailMessage
from pathlib import Path
from zoneinfo import ZoneInfo

from tradeops.app.models import PortfolioState
from tradeops.app.tlh_daily import build_daily_tlh_input, load_tlh_etf_map


OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
DEFAULT_MODEL = "google/gemini-3-flash-preview"


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate and email a daily TLH report.")
    parser.add_argument("--portfolio-json", required=True, help="Path to CLI portfolio JSON.")
    parser.add_argument("--prompt-file", required=True, help="Path to the user-editable TLH prompt.")
    parser.add_argument("--etf-map", required=True, help="Path to the local ETF TLH mapping JSON.")
    parser.add_argument("--output-markdown", required=True, help="Path to write the markdown report.")
    parser.add_argument("--output-payload", required=True, help="Path to write the deterministic TLH payload JSON.")
    return parser.parse_args()


def _build_llm_input(portfolio_path: Path, prompt_path: Path, etf_map_path: Path) -> tuple[dict, str]:
    portfolio = PortfolioState.model_validate_json(portfolio_path.read_text())
    as_of = portfolio.captured_at.astimezone(ZoneInfo("America/New_York"))
    etf_map = load_tlh_etf_map(etf_map_path)
    digest = build_daily_tlh_input(portfolio, etf_map, as_of=as_of)
    prompt = prompt_path.read_text()
    return json.loads(digest.model_dump_json(indent=2)), prompt


def _call_openrouter(payload: dict, prompt: str) -> str:
    api_key = os.environ["OPENROUTER_API_KEY"]
    model = os.environ.get("OPENROUTER_MODEL", DEFAULT_MODEL)
    body = {
        "model": model,
        "temperature": 0.2,
        "messages": [
            {
                "role": "system",
                "content": "You are a concise financial-advisor style report writer. Return markdown only with no code fences.",
            },
            {
                "role": "user",
                "content": (
                    prompt.strip()
                    + "\n\n## Deterministic TLH Input\n\n"
                    + json.dumps(payload, indent=2)
                ),
            },
        ],
    }
    request = urllib.request.Request(
        OPENROUTER_URL,
        data=json.dumps(body).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": os.environ.get("OPENROUTER_SITE_URL", "https://github.com/arox7/alpaca-cli"),
            "X-Title": os.environ.get("OPENROUTER_APP_NAME", "tradeops-daily-tlh"),
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request) as response:
            raw = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"OpenRouter request failed: {exc.code} {detail}") from exc

    choices = raw.get("choices", [])
    if not choices:
        raise RuntimeError("OpenRouter returned no choices.")
    message = choices[0].get("message", {})
    content = message.get("content", "")
    if isinstance(content, list):
        parts = [part.get("text", "") for part in content if isinstance(part, dict)]
        content = "".join(parts)
    if not isinstance(content, str) or not content.strip():
        raise RuntimeError("OpenRouter returned an empty report.")
    return content.strip()


def _send_email(markdown_report: str, as_of: datetime) -> None:
    recipient = os.environ["TLH_REPORT_TO_EMAIL"]
    sender = os.environ["TLH_REPORT_FROM_EMAIL"]
    smtp_host = os.environ["SMTP_HOST"]
    smtp_port = int(os.environ.get("SMTP_PORT", "587"))
    smtp_username = os.environ["SMTP_USERNAME"]
    smtp_password = os.environ["SMTP_PASSWORD"]

    message = EmailMessage()
    message["Subject"] = f"Daily TLH Report | {as_of.strftime('%Y-%m-%d')}"
    message["From"] = sender
    message["To"] = recipient
    message.set_content(markdown_report)

    if smtp_port == 465:
        with smtplib.SMTP_SSL(smtp_host, smtp_port) as server:
            server.login(smtp_username, smtp_password)
            server.send_message(message)
        return

    with smtplib.SMTP(smtp_host, smtp_port) as server:
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(smtp_username, smtp_password)
        server.send_message(message)


def main() -> None:
    args = _parse_args()
    portfolio_path = Path(args.portfolio_json)
    prompt_path = Path(args.prompt_file)
    etf_map_path = Path(args.etf_map)
    output_markdown = Path(args.output_markdown)
    output_payload = Path(args.output_payload)

    payload, prompt = _build_llm_input(portfolio_path, prompt_path, etf_map_path)
    output_payload.write_text(json.dumps(payload, indent=2) + "\n")

    report = _call_openrouter(payload, prompt)
    output_markdown.write_text(report + "\n")

    as_of = datetime.fromisoformat(payload["as_of"])
    _send_email(report, as_of)

    print(f"Wrote report to {output_markdown}")
    print(f"Wrote payload to {output_payload}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        raise
