"""Renders the workbook HTML to a PDF using the pre-installed Chromium via Playwright."""

from __future__ import annotations

from pathlib import Path


def _launch_chromium(p):
    try:
        return p.chromium.launch()
    except Exception:
        # Falls back to a known pre-installed binary (used in this dev sandbox);
        # on your own machine, `playwright install chromium` makes this unnecessary.
        return p.chromium.launch(executable_path="/opt/pw-browsers/chromium", args=["--no-sandbox"])


def render_pdf(html: str, output_path: str | Path) -> Path:
    from playwright.sync_api import sync_playwright

    output_path = Path(output_path)
    with sync_playwright() as p:
        browser = _launch_chromium(p)
        page = browser.new_page()
        page.set_content(html, wait_until="networkidle")
        page.pdf(
            path=str(output_path),
            format="A4",
            print_background=True,
            margin={"top": "20mm", "bottom": "20mm", "left": "15mm", "right": "15mm"},
        )
        browser.close()
    return output_path
