from __future__ import annotations

import argparse
import html
import json
import os
import re
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


def _format_inline_markdown(text: str) -> str:
    escaped = html.escape(text)
    escaped = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
    escaped = re.sub(r"`(.+?)`", r"<code>\1</code>", escaped)
    return escaped


def markdown_to_html(markdown_report: str) -> str:
    lines = [line.rstrip() for line in markdown_report.strip().splitlines()]
    blocks: list[str] = []
    i = 0

    while i < len(lines):
        line = lines[i]
        if not line.strip():
            i += 1
            continue

        if line.startswith("## "):
            blocks.append(f"<h2>{_format_inline_markdown(line[3:])}</h2>")
            i += 1
            continue

        if line.startswith("### "):
            blocks.append(f"<h3>{_format_inline_markdown(line[4:])}</h3>")
            i += 1
            continue

        if line.startswith("|"):
            table_lines: list[str] = []
            while i < len(lines) and lines[i].startswith("|"):
                table_lines.append(lines[i])
                i += 1
            rows = []
            for table_line in table_lines:
                cells = [cell.strip() for cell in table_line.strip("|").split("|")]
                rows.append(cells)
            if len(rows) >= 2:
                header = rows[0]
                body = rows[2:]
                thead = "".join(f"<th>{_format_inline_markdown(cell)}</th>" for cell in header)
                tbody_rows = []
                for row in body:
                    tbody_rows.append(
                        "<tr>" + "".join(f"<td>{_format_inline_markdown(cell)}</td>" for cell in row) + "</tr>"
                    )
                blocks.append(
                    '<table class="report-table"><thead><tr>'
                    + thead
                    + "</tr></thead><tbody>"
                    + "".join(tbody_rows)
                    + "</tbody></table>"
                )
            continue

        if line.startswith("- "):
            items: list[str] = []
            while i < len(lines) and lines[i].startswith("- "):
                items.append(lines[i][2:])
                i += 1
            blocks.append(
                "<ul>" + "".join(f"<li>{_format_inline_markdown(item)}</li>" for item in items) + "</ul>"
            )
            continue

        paragraph_lines = [line]
        i += 1
        while i < len(lines) and lines[i].strip() and not lines[i].startswith(("## ", "### ", "|", "- ")):
            paragraph_lines.append(lines[i])
            i += 1
        paragraph = " ".join(part.strip() for part in paragraph_lines)
        blocks.append(f"<p>{_format_inline_markdown(paragraph)}</p>")

    return (
        "<html><head><style>"
        "body{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Arial,sans-serif;"
        "line-height:1.5;color:#111827;padding:20px;max-width:900px;margin:0 auto;}"
        "h2,h3{color:#0f172a;margin:24px 0 12px;}"
        "p{margin:12px 0;}"
        ".report-table{border-collapse:collapse;width:100%;margin:14px 0 22px;}"
        ".report-table th,.report-table td{border:1px solid #d1d5db;padding:8px 10px;text-align:left;vertical-align:top;}"
        ".report-table th{background:#f3f4f6;font-weight:600;}"
        "code{background:#f3f4f6;padding:1px 4px;border-radius:4px;}"
        "ul{margin:12px 0 18px 20px;}"
        "</style></head><body>"
        + "".join(blocks)
        + "</body></html>"
    )


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
    message.add_alternative(markdown_to_html(markdown_report), subtype="html")

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
