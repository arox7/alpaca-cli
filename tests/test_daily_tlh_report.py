from __future__ import annotations

from scripts.daily_tlh_report import markdown_to_html


def test_markdown_to_html_renders_tables_and_headings() -> None:
    markdown = """## Daily TLH Report

Short takeaway sentence.

### Summary

| Metric | Value |
| --- | ---: |
| Total Visible Losses | $12,236 |
| Candidates | 4 |

### Action

- Review `UPRO`
- Avoid **gray** swaps by default
"""

    html = markdown_to_html(markdown)

    assert "<h2>Daily TLH Report</h2>" in html
    assert "<h3>Summary</h3>" in html
    assert "<table" in html
    assert "<th>Metric</th>" in html
    assert "<td>Total Visible Losses</td>" in html
    assert "<li>Review <code>UPRO</code></li>" in html
    assert "<strong>gray</strong>" in html
