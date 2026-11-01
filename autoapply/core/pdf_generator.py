"""HTML → PDF resume generator using Jinja2 + WeasyPrint."""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader
from weasyprint import HTML

from autoapply.utils.logger import get_logger

logger = get_logger(__name__)

# Resolve the package templates directory
_PACKAGE_DIR = Path(__file__).resolve().parent.parent
_DEFAULT_TEMPLATE_DIR = _PACKAGE_DIR / "templates"


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

    # Ensure output directory exists
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)

    logger.info(f"Generating PDF → {out}")
    HTML(string=html_content).write_pdf(str(out))

    return str(out.resolve())
