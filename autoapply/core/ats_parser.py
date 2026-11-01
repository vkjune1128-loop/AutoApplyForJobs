"""ATS resume parser — extract text from PDF as an ATS would see it."""

from __future__ import annotations

import re
from io import BytesIO
from pathlib import Path

from pdfminer.high_level import extract_text
from pdfminer.layout import LAParams

from autoapply.utils.logger import get_logger

logger = get_logger(__name__)


def parse_resume_pdf(pdf_path: str) -> str:
    """Extract raw text from a PDF resume using pdfminer.

    This simulates what an Applicant Tracking System sees when parsing
    your resume — no formatting, just plain text.

    Args:
        pdf_path: Path to the PDF file.

    Returns:
        Extracted text content.
    """
    logger.info(f"Parsing PDF: {pdf_path}")

    laparams = LAParams(
        line_margin=0.5,
        word_margin=0.1,
        char_margin=2.0,
        boxes_flow=0.5,
    )

    text = extract_text(pdf_path, laparams=laparams)
    return text.strip()


def check_ats_compatibility(pdf_path: str) -> dict:
    """Check a PDF resume for ATS compatibility issues.

    Args:
        pdf_path: Path to the PDF file.

    Returns:
        Dict with text_extractable, has_tables, has_images, word_count, and warnings.
    """
    logger.info(f"Checking ATS compatibility: {pdf_path}")

    warnings: list[str] = []

    # Try text extraction
    try:
        text = parse_resume_pdf(pdf_path)
        text_extractable = len(text.strip()) > 50
    except Exception as e:
        logger.error(f"Failed to extract text: {e}")
        text = ""
        text_extractable = False
        warnings.append(f"Text extraction failed: {e}")

    if not text_extractable:
        warnings.append(
            "Very little text could be extracted. Resume may be image-based or use non-standard fonts."
        )

    # Word count
    words = text.split()
    word_count = len(words)

    if word_count < 100:
        warnings.append(f"Resume has only {word_count} words — too short for most roles.")
    elif word_count > 1200:
        warnings.append(f"Resume has {word_count} words — consider trimming to 1-2 pages.")

    # Heuristic: detect true tabular structures (e.g. multi-cell markdown tables with separators or tab-separated columns)
    has_tables = bool(re.search(r"(\|\s*[-:]+[-|\s:]*\|)|(\t{2,})", text))
    if has_tables:
        warnings.append("Tables detected — some ATS systems struggle with tabular layouts.")

    # Check for image indicators in raw PDF bytes
    has_images = False
    try:
        raw_bytes = Path(pdf_path).read_bytes()
        # Look for image XObjects in PDF stream
        has_images = b"/Image" in raw_bytes or b"/XObject" in raw_bytes
    except Exception:
        pass

    if has_images:
        warnings.append(
            "Images detected in PDF. ATS cannot read text embedded in images."
        )

    # Check for common issues
    if re.search(r"[\u2022\u25cf\u25cb\u25aa]", text):
        # Bullet characters are fine — just verify they parse correctly
        pass

    # Check for contact info
    has_email = bool(re.search(r"[\w.+-]+@[\w-]+\.[\w.-]+", text))
    has_phone = bool(re.search(r"[\+]?[\d\s\-\(\)]{7,}", text))

    if not has_email:
        warnings.append("No email address detected — ensure contact info is in text, not an image.")
    if not has_phone:
        warnings.append("No phone number detected — ensure contact info is in text, not an image.")

    return {
        "text_extractable": text_extractable,
        "has_tables": has_tables,
        "has_images": has_images,
        "word_count": word_count,
        "warnings": warnings,
    }
