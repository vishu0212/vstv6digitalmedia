
"""Generate a Telugu newspaper PDF for VSTV6 Digital Media."""

from __future__ import annotations

import io
import logging
import re
from datetime import date, datetime
from urllib.parse import urlparse
from pathlib import Path

import requests

from flask import current_app
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    Image,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

from models import Article
from models.article import contains_telugu_script, is_telugu_summary


logger = logging.getLogger(__name__)

PAGE_WIDTH, PAGE_HEIGHT = A4
MARGIN = 12 * mm

BASE_DIRECTORY = Path(__file__).resolve().parent.parent
FONT_DIRECTORY = BASE_DIRECTORY / "static" / "fonts"

TELUGU_FONT_PATH = FONT_DIRECTORY / "NotoSansTelugu-Regular.ttf"
TELUGU_BOLD_FONT_PATH = FONT_DIRECTORY / "NotoSansTelugu-Bold.ttf"

FONT_REGISTERED = False
TELUGU_CHAR_RE = re.compile(r"[\u0C00-\u0C7F]")


# ---------------------------------------------------------
# FONT REGISTRATION
# ---------------------------------------------------------

def register_newspaper_fonts() -> bool:
    """Register Telugu fonts required for newspaper generation."""
    global FONT_REGISTERED

    if FONT_REGISTERED:
        return True

    if not TELUGU_FONT_PATH.is_file():
        logger.error("Telugu font not found: %s", TELUGU_FONT_PATH)
        return False

    try:
        pdfmetrics.registerFont(
            TTFont("VSTV6Telugu", str(TELUGU_FONT_PATH))
        )

        bold_font_path = (
            TELUGU_BOLD_FONT_PATH
            if TELUGU_BOLD_FONT_PATH.is_file()
            else TELUGU_FONT_PATH
        )

        pdfmetrics.registerFont(
            TTFont("VSTV6TeluguBold", str(bold_font_path))
        )

        FONT_REGISTERED = True
        return True

    except Exception:
        logger.exception("Failed to register Telugu PDF fonts")
        return False


# ---------------------------------------------------------
# PDF STYLES
# ---------------------------------------------------------

def get_styles():
    """Create styles for the Telugu newspaper."""
    styles = getSampleStyleSheet()

    styles.add(
        ParagraphStyle(
            name="NewsMasthead",
            parent=styles["Title"],
            fontName="VSTV6TeluguBold",
            fontSize=25,
            leading=32,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#102A43"),
            spaceAfter=3 * mm,
        )
    )

    styles.add(
        ParagraphStyle(
            name="NewsEdition",
            parent=styles["Normal"],
            fontName="VSTV6Telugu",
            fontSize=9,
            leading=13,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#52606D"),
        )
    )

    styles.add(
        ParagraphStyle(
            name="NewsHeadline",
            parent=styles["Heading2"],
            fontName="VSTV6TeluguBold",
            fontSize=15,
            leading=21,
            alignment=TA_LEFT,
            textColor=colors.HexColor("#102A43"),
            spaceBefore=2 * mm,
            spaceAfter=2 * mm,
            keepWithNext=True,
        )
    )

    styles.add(
        ParagraphStyle(
            name="NewsSummary",
            parent=styles["Normal"],
            fontName="VSTV6TeluguBold",
            fontSize=10,
            leading=16,
            alignment=TA_JUSTIFY,
            textColor=colors.HexColor("#334E68"),
            spaceAfter=3 * mm,
        )
    )

    styles.add(
        ParagraphStyle(
            name="NewsBody",
            parent=styles["Normal"],
            fontName="VSTV6Telugu",
            fontSize=9,
            leading=14,
            alignment=TA_JUSTIFY,
            textColor=colors.HexColor("#243B53"),
            spaceAfter=3 * mm,
            splitLongWords=True,
        )
    )

    styles.add(
        ParagraphStyle(
            name="NewsMeta",
            parent=styles["Normal"],
            fontName="VSTV6Telugu",
            fontSize=8,
            leading=11,
            textColor=colors.HexColor("#627D98"),
            spaceAfter=2 * mm,
        )
    )

    styles.add(
        ParagraphStyle(
            name="NewsNotice",
            parent=styles["Normal"],
            fontName="VSTV6Telugu",
            fontSize=10,
            leading=15,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#9B2C2C"),
        )
    )

    return styles


# ---------------------------------------------------------
# TEXT HELPERS
# ---------------------------------------------------------

def escape_pdf_text(value) -> str:
    """Escape text before passing it to ReportLab Paragraph."""
    if value is None:
        return ""

    text = str(value)

    replacements = {
        "&": "&amp;",
        "<": "&lt;",
        ">": "&gt;",
        '"': "&quot;",
        "'": "&#39;",
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    return text


def format_date(value) -> str:
    """Format a date or datetime for display."""
    if not value:
        return date.today().strftime("%d-%m-%Y")

    if isinstance(value, (date, datetime)):
        return value.strftime("%d-%m-%Y")

    return str(value)


def get_article_title(article) -> str:
    """Return the Telugu headline when available."""
    title = (getattr(article, "title_te", None) or "").strip()
    return title if contains_telugu_script(title) else ""


def get_article_summary(article) -> str:
    """Return the Telugu summary when available."""
    summary = (getattr(article, "summary_te", None) or "").strip()
    return summary if is_telugu_summary(summary) else ""


def get_article_body(article) -> str:
    """Return the Telugu article body without appended source-link lines."""
    telugu_body = (getattr(article, "body_te", None) or "").strip()
    if TELUGU_CHAR_RE.search(telugu_body):
        body = telugu_body
    else:
        legacy_body = (getattr(article, "body_en", None) or "").strip()
        body = legacy_body if TELUGU_CHAR_RE.search(legacy_body) else ""

    body = "\n".join(
        line
        for line in body.splitlines()
        if not re.match(
            r"^\s*(?:(?:మూల వార్త|Original report)\s*:\s*)?https?://\S+\s*$",
            line,
            flags=re.IGNORECASE,
        )
    ).strip()
    body = re.sub(r"https?://\S+", "", body, flags=re.IGNORECASE)
    body = re.sub(
        r"(?im)^\s*(?:మూల వార్త|Original report)\s*:?.*$",
        "",
        body,
    )
    body = re.sub(r"[ \t]+", " ", body)
    body = re.sub(r"\n{3,}", "\n\n", body).strip()
    return body if contains_telugu_script(body) else ""


# ---------------------------------------------------------
# ARTICLE QUERIES
# ---------------------------------------------------------

def get_published_articles():
    """Retrieve published Telugu articles that contain body text."""
    return (
        Article.query
        .filter(Article.status == "published")
        .order_by(
            Article.published_at.desc(),
            Article.created_at.desc(),
        )
        .all()
    )


def prepare_articles(articles):
    """Keep only published Telugu articles with full body text."""
    prepared = []

    for article in articles:
        if getattr(article, "status", None) != "published":
            continue

        if not get_article_title(article) or not get_article_body(article):
            continue

        prepared.append(article)

    return prepared


# ---------------------------------------------------------
# IMAGE HANDLING
# ---------------------------------------------------------

def download_article_image(image_url: str):
    """Download a public article image with size restrictions."""
    if not image_url:
        return None

    try:
        parsed = urlparse(image_url)

        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            return None

        with requests.get(
            image_url,
            timeout=10,
            stream=True,
            headers={"User-Agent": "VSTV6DigitalMedia/1.0"},
        ) as response:
            response.raise_for_status()

            content_type = response.headers.get(
                "Content-Type", ""
            ).lower()

            if not content_type.startswith("image/"):
                return None

            max_bytes = 5 * 1024 * 1024
            content_length = response.headers.get("Content-Length")

            if content_length:
                try:
                    if int(content_length) > max_bytes:
                        return None
                except ValueError:
                    pass

            buffer = io.BytesIO()
            total = 0

            for chunk in response.iter_content(chunk_size=8192):
                if not chunk:
                    continue

                total += len(chunk)

                if total > max_bytes:
                    return None

                buffer.write(chunk)

            buffer.seek(0)
            return buffer

    except (requests.RequestException, ValueError):
        logger.warning(
            "Could not download newspaper image: %s",
            image_url,
        )
        return None


# ---------------------------------------------------------
# PAGE HEADER AND FOOTER
# ---------------------------------------------------------

def draw_page(canvas, doc):
    """Draw the newspaper header line and footer."""
    canvas.saveState()

    page_number = canvas.getPageNumber()

    canvas.setStrokeColor(colors.HexColor("#102A43"))
    canvas.setLineWidth(0.8)
    canvas.line(
        MARGIN,
        PAGE_HEIGHT - 8 * mm,
        PAGE_WIDTH - MARGIN,
        PAGE_HEIGHT - 8 * mm,
    )

    canvas.setStrokeColor(colors.HexColor("#BCCCDC"))
    canvas.line(
        MARGIN,
        9 * mm,
        PAGE_WIDTH - MARGIN,
        9 * mm,
    )

    canvas.setFont("VSTV6Telugu", 8)
    canvas.setFillColor(colors.HexColor("#52606D"))

    canvas.drawString(
        MARGIN,
        5 * mm,
        "VSTV6 Digital Media",
    )

    canvas.drawRightString(
        PAGE_WIDTH - MARGIN,
        5 * mm,
        f"Page {page_number}",
    )

    canvas.restoreState()


# ---------------------------------------------------------
# NEWSPAPER PDF GENERATOR
# ---------------------------------------------------------

def generate_newspaper_pdf(articles=None, edition_date=None):
    """
    Generate a Telugu newspaper PDF.

    If articles are supplied, generate the newspaper from those
    selected articles. Otherwise, query eligible published articles.

    Returns:
        io.BytesIO: PDF file positioned at the beginning.
    """
    if not register_newspaper_fonts():
        raise RuntimeError(
            "Telugu font file is missing. Add "
            "NotoSansTelugu-Regular.ttf to static/fonts."
        )

    if articles is None:
        articles = get_published_articles()

    articles = prepare_articles(articles)

    if not articles:
        raise ValueError(
            "No selected published Telugu articles with full body "
            "text were found. Check article language, publication "
            "status, and body_te fields."
        )

    if isinstance(edition_date, (date, datetime)):
        edition_date_text = edition_date.strftime("%d-%m-%Y")
    elif edition_date:
        edition_date_text = str(edition_date)
    else:
        edition_date_text = date.today().strftime("%d-%m-%Y")

    output = io.BytesIO()

    doc = BaseDocTemplate(
        output,
        pagesize=A4,
        rightMargin=MARGIN,
        leftMargin=MARGIN,
        topMargin=15 * mm,
        bottomMargin=15 * mm,
        title="VSTV6 Digital Media - Telugu Newspaper",
        author="VSTV6 Digital Media",
    )

    frame = Frame(
        MARGIN,
        MARGIN,
        PAGE_WIDTH - (2 * MARGIN),
        PAGE_HEIGHT - (2 * MARGIN),
        id="newspaper-frame",
    )

    doc.addPageTemplates(
        [
            PageTemplate(
                id="newspaper",
                frames=[frame],
                onPage=draw_page,
            )
        ]
    )

    styles = get_styles()
    story = []

    # Newspaper masthead.
    story.append(
        Paragraph(
            "VSTV6 డిజిటల్ మీడియా",
            styles["NewsMasthead"],
        )
    )

    story.append(
        Paragraph(
            (
                "తెలుగు వార్తా పత్రిక | "
                f"{escape_pdf_text(edition_date_text)}"
            ),
            styles["NewsEdition"],
        )
    )

    story.append(Spacer(1, 3 * mm))

    divider = Table(
        [[""]],
        colWidths=[PAGE_WIDTH - (2 * MARGIN)],
        rowHeights=[1.2 * mm],
    )

    divider.setStyle(
        TableStyle(
            [
                (
                    "BACKGROUND",
                    (0, 0),
                    (-1, -1),
                    colors.HexColor("#102A43"),
                ),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )

    story.append(divider)
    story.append(Spacer(1, 5 * mm))

    printed_articles = 0

    for article in articles:
        body = get_article_body(article)

        # prepare_articles() already checks this, but retain
        # the guard to avoid printing an empty article.
        if not body:
            continue

        title = escape_pdf_text(get_article_title(article))
        story.append(
            Paragraph(
                title,
                styles["NewsHeadline"],
            )
        )

        image_url = getattr(article, "image_url", None)
        if image_url:
            image_buffer = download_article_image(image_url)
            if image_buffer:
                try:
                    image = Image(
                        image_buffer,
                        width=110 * mm,
                        height=70 * mm,
                        kind="proportional",
                    )
                    image.hAlign = "LEFT"
                    story.append(image)
                    story.append(Spacer(1, 3 * mm))
                except Exception:
                    logger.exception(
                        "Could not place image for article %s",
                        getattr(article, "id", "unknown"),
                    )

        paragraphs = [
            paragraph.strip()
            for paragraph in (
                body.replace("\r\n", "\n")
                .replace("\r", "\n")
                .split("\n")
            )
            if paragraph.strip()
        ]

        for paragraph in paragraphs:
            story.append(
                Paragraph(
                    escape_pdf_text(paragraph),
                    styles["NewsBody"],
                )
            )

        story.append(Spacer(1, 5 * mm))

        separator = Table(
            [[""]],
            colWidths=[PAGE_WIDTH - (2 * MARGIN)],
            rowHeights=[0.5 * mm],
        )

        separator.setStyle(
            TableStyle(
                [
                    (
                        "BACKGROUND",
                        (0, 0),
                        (-1, -1),
                        colors.HexColor("#D9E2EC"),
                    ),
                    ("LEFTPADDING", (0, 0), (-1, -1), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ]
            )
        )

        story.append(separator)
        story.append(Spacer(1, 4 * mm))

        printed_articles += 1

    if printed_articles == 0:
        raise ValueError(
            "No Telugu article bodies are available to print."
        )

    try:
        doc.build(story)
    except Exception:
        logger.exception("Failed to build Telugu newspaper PDF")
        raise

    output.seek(0)
    return output


# ---------------------------------------------------------
# ROUTE-COMPATIBLE FUNCTION
# ---------------------------------------------------------

def create_newspaper_pdf(articles, edition_date=None):
    """
    Generate a PDF from the articles selected in the admin interface.

    This is the function imported by routes/newspaper.py.
    """
    return generate_newspaper_pdf(
        articles=articles,
        edition_date=edition_date,
    )
