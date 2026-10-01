"""Shared HTML → PDF rendering (xhtml2pdf) with embedded Greek fonts."""

from __future__ import annotations

import io
from pathlib import Path

from django.conf import settings
from django.template.loader import render_to_string
from reportlab.lib.fonts import addMapping
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from xhtml2pdf import default as xhtml2pdf_default
from xhtml2pdf import pisa

STATIC_DIR = Path(settings.BASE_DIR) / "static"
PDF_FONT_FAMILY = "DejaVuSans"
PDF_FONT_FILES = {
    PDF_FONT_FAMILY: STATIC_DIR / "fonts" / "DejaVuSans.ttf",
    f"{PDF_FONT_FAMILY}-Bold": STATIC_DIR / "fonts" / "DejaVuSans-Bold.ttf",
}
PDF_ASSETS = {"logo_url": "img/cy_logo.png"}


def ensure_pdf_fonts() -> None:
    """Register DejaVu Sans (regular + bold) so CSS `font-family: DejaVuSans` works.

    The fonts are registered with reportlab instead of CSS @font-face: on Windows xhtml2pdf
    copies @font-face files to a locked temporary file that reportlab cannot reopen.
    """
    registered = pdfmetrics.getRegisteredFontNames()
    for font_name, path in PDF_FONT_FILES.items():
        if font_name not in registered:
            pdfmetrics.registerFont(TTFont(font_name, str(path)))
    bold = f"{PDF_FONT_FAMILY}-Bold"
    for is_bold, is_italic, font_name in (
        (0, 0, PDF_FONT_FAMILY),
        (0, 1, PDF_FONT_FAMILY),
        (1, 0, bold),
        (1, 1, bold),
    ):
        addMapping(PDF_FONT_FAMILY, is_bold, is_italic, font_name)
    xhtml2pdf_default.DEFAULT_FONT[PDF_FONT_FAMILY.lower()] = PDF_FONT_FAMILY


def _static_link_callback(uri: str, rel: str) -> str:
    """Resolve /static/... references of the PDF templates to local files."""
    if uri.startswith(settings.STATIC_URL):
        path = STATIC_DIR / uri.removeprefix(settings.STATIC_URL)
        if path.is_file():
            return str(path)
    return uri


def render_pdf(template_name: str, context: dict) -> bytes:
    ensure_pdf_fonts()
    assets = {name: f"{settings.STATIC_URL}{relative}" for name, relative in PDF_ASSETS.items()}
    html = render_to_string(template_name, {**assets, **context})
    buffer = io.BytesIO()
    result = pisa.CreatePDF(
        html, dest=buffer, encoding="utf-8", link_callback=_static_link_callback
    )
    if result.err:
        raise RuntimeError("PDF generation failed.")
    return buffer.getvalue()


def safe_case_number(case_number: str) -> str:
    return case_number.replace("/", "-").replace("\\", "-")
