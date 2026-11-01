"""HTML → PDF resume generator using Jinja2 with WeasyPrint / Playwright engines."""

from __future__ import annotations

import os
import sys
from pathlib import Path

# On macOS Apple Silicon / Intel, ensure Homebrew libraries (pango, gobject) are discoverable
if sys.platform == "darwin":
    current_fallback = os.environ.get("DYLD_FALLBACK_LIBRARY_PATH", "")
    homebrew_libs = ["/opt/homebrew/lib", "/usr/local/lib"]
    paths = [p for p in homebrew_libs if Path(p).exists()]
    if current_fallback:
        paths.append(current_fallback)
    os.environ["DYLD_FALLBACK_LIBRARY_PATH"] = ":".join(paths)

from jinja2 import Environment, FileSystemLoader

from autoapply.utils.logger import get_logger

logger = get_logger(__name__)

# Resolve the package templates directory
_PACKAGE_DIR = Path(__file__).resolve().parent.parent
_DEFAULT_TEMPLATE_DIR = _PACKAGE_DIR / "templates"


def _generate_pdf_playwright(html_content: str, output_path: Path) -> None:
    """Fallback PDF generator using Playwright headless Chromium."""
    from playwright.sync_api import sync_playwright

    logger.info("Using Playwright Chromium engine for PDF generation")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_content(html_content, wait_until="load")
        page.pdf(
            path=str(output_path),
            format="Letter",
            margin={"top": "0.4in", "bottom": "0.4in", "left": "0.5in", "right": "0.5in"},
            print_background=True,
        )
        browser.close()


def generate_resume_pdf(
    resume_data: dict,
    output_path: str,
    template_path: str | None = None,
) -> str:
    """Render a resume from a Jinja2 HTML template to a PDF.

    Args:
        resume_data: Dict of resume fields (matches TailoredResume / ResumeData schema).
        output_path: Filesystem path for the generated PDF.
        template_path: Optional path to a custom Jinja2 HTML template.
            Defaults to the bundled ``templates/resume.html``.

    Returns:
        The absolute path to the generated PDF.
    """
    if template_path:
        tpl_path = Path(template_path)
        template_dir = str(tpl_path.parent)
        template_name = tpl_path.name
    else:
        template_dir = str(_DEFAULT_TEMPLATE_DIR)
        template_name = "resume.html"

    logger.info(f"Rendering resume template: {template_dir}/{template_name}")

    env = Environment(
        loader=FileSystemLoader(template_dir),
        autoescape=True,
    )
    template = env.get_template(template_name)
    html_content = template.render(**resume_data)

    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    # Save HTML alongside PDF for easy preview / debugging
    html_preview_path = out.with_suffix(".html")
    html_preview_path.write_text(html_content, encoding="utf-8")

    logger.info(f"Generating PDF → {out}")

    # Try WeasyPrint first; fall back to Playwright Chromium
    try:
        from weasyprint import HTML

        HTML(string=html_content).write_pdf(str(out))
    except Exception as e:
        logger.warning(f"WeasyPrint unavailable or failed ({e}), falling back to Playwright engine")
        _generate_pdf_playwright(html_content, out)

    return str(out.resolve())
