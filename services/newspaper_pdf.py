"""Generate a professional Telugu newspaper PDF for VSTV6 Digital Media."""

from __future__ import annotations

import io
import logging
import re
from datetime import date, datetime
from pathlib import Path
from urllib.parse import urlparse

import requests

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas as reportlab_canvas
from reportlab.platypus import (
    BaseDocTemplate,
    CondPageBreak,
    Frame,
    FrameBreak,
    Flowable,
    Image,
    KeepTogether,
    NextPageTemplate,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

from models import Article
from models.article import contains_telugu_script, is_telugu_summary


logger = logging.getLogger(__name__)


# =========================================================
# CONFIGURATION
# =========================================================

PAGE_WIDTH, PAGE_HEIGHT = A4

MARGIN = 10 * mm

# Two-column newspaper layout
COLUMN_COUNT = 2
COLUMN_GAP = 5 * mm

HEADER_HEIGHT = 11 * mm
FOOTER_HEIGHT = 12 * mm

MASTHEAD_HEIGHT = 50 * mm
LEAD_HEIGHT = 56 * mm

BASE_DIRECTORY = Path(__file__).resolve().parent.parent

FONT_DIRECTORY = BASE_DIRECTORY / "static" / "fonts"

TELUGU_FONT_PATH = FONT_DIRECTORY / "NotoSerifTelugu-Regular.ttf"
TELUGU_BOLD_FONT_PATH = FONT_DIRECTORY / "NotoSerifTelugu-Bold.ttf"

MASTHEAD_IMAGE_PATH = (
    BASE_DIRECTORY
    / "static"
    / "images"
    / "vstv6-newspaper-header.png"
)

FONT_REGISTERED = False

TELUGU_CHAR_RE = re.compile(r"[\u0C00-\u0C7F]")


# =========================================================
# FONT REGISTRATION
# =========================================================

def register_newspaper_fonts() -> bool:
    global FONT_REGISTERED

    if FONT_REGISTERED:
        return True

    if not TELUGU_FONT_PATH.is_file():
        raise FileNotFoundError(
            f"Telugu regular font not found: {TELUGU_FONT_PATH}"
        )

    if not TELUGU_BOLD_FONT_PATH.is_file():
        raise FileNotFoundError(
            f"Telugu bold font not found: {TELUGU_BOLD_FONT_PATH}"
        )

    registered = pdfmetrics.getRegisteredFontNames()

    if "VSTV6Telugu" not in registered:
        pdfmetrics.registerFont(
            TTFont("VSTV6Telugu", str(TELUGU_FONT_PATH))
        )

    if "VSTV6TeluguBold" not in registered:
        pdfmetrics.registerFont(
            TTFont("VSTV6TeluguBold", str(TELUGU_BOLD_FONT_PATH))
        )

    pdfmetrics.registerFontFamily(
        "VSTV6Telugu",
        normal="VSTV6Telugu",
        bold="VSTV6TeluguBold",
        italic="VSTV6Telugu",
        boldItalic="VSTV6TeluguBold",
    )

    FONT_REGISTERED = True
    return True


# =========================================================
# PDF STYLES
# =========================================================

def get_styles():

    styles = getSampleStyleSheet()

    styles.add(
        ParagraphStyle(
            name="NewsEdition",
            fontName="VSTV6Telugu",
            fontSize=8,
            leading=10,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#52606D"),
        )
    )

    styles.add(
        ParagraphStyle(
            name="NewsKicker",
            fontName="VSTV6TeluguBold",
            fontSize=8,
            leading=10,
            alignment=TA_LEFT,
            textColor=colors.white,
        )
    )

    styles.add(
        ParagraphStyle(
            name="NewsHeadline",
            fontName="VSTV6TeluguBold",
            fontSize=13,
            leading=17,
            alignment=TA_LEFT,
            textColor=colors.HexColor("#102A43"),
            spaceBefore=1 * mm,
            spaceAfter=1.5 * mm,
            keepWithNext=True,
            splitLongWords=True,
        )
    )

    styles.add(
        ParagraphStyle(
            name="NewsLeadHeadline",
            fontName="VSTV6TeluguBold",
            fontSize=24,
            leading=32,
            alignment=TA_LEFT,
            textColor=colors.HexColor("#102A43"),
            spaceBefore=1 * mm,
            spaceAfter=1 * mm,
            splitLongWords=True,
        )
    )

    styles.add(
        ParagraphStyle(
            name="NewsSummary",
            fontName="VSTV6Telugu",
            fontSize=9,
            leading=12,
            alignment=TA_JUSTIFY,
            textColor=colors.HexColor("#334E68"),
            spaceAfter=2 * mm,
        )
    )

    styles.add(
        ParagraphStyle(
            name="NewsBody",
            fontName="VSTV6Telugu",
            fontSize=9,
            leading=12,
            alignment=TA_JUSTIFY,
            textColor=colors.HexColor("#263442"),
            spaceAfter=1.5 * mm,
            splitLongWords=True,
            allowWidows=0,
            allowOrphans=0,
        )
    )

    styles.add(
        ParagraphStyle(
            name="NewsMeta",
            fontName="VSTV6Telugu",
            fontSize=7,
            leading=9,
            textColor=colors.HexColor("#627D98"),
            spaceAfter=1 * mm,
        )
    )

    styles.add(
        ParagraphStyle(
            name="NewsNotice",
            fontName="VSTV6Telugu",
            fontSize=9,
            leading=12,
            alignment=TA_CENTER,
            textColor=colors.HexColor("#9B2C2C"),
        )
    )

    return styles


# =========================================================
# TEXT HELPERS
# =========================================================

def escape_pdf_text(value) -> str:

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

    if not value:
        return date.today().strftime("%Y-%m-%d")

    if isinstance(value, (date, datetime)):
        return value.strftime("%Y-%m-%d")

    return str(value)


def get_article_title(article) -> str:

    title = (getattr(article, "title_te", None) or "").strip()

    if contains_telugu_script(title):
        return title

    return ""


def get_article_summary(article) -> str:

    summary = (getattr(article, "summary_te", None) or "").strip()

    if is_telugu_summary(summary):
        return summary

    return ""


# =========================================================
# ARTICLE CLEANING
# =========================================================

def split_article_body(body: str, max_words: int = 20):
    """Split a story body into an opening segment and the remaining copy."""
    text = (body or "").strip()

    if not text or max_words <= 0:
        return text, ""

    words = text.split()

    if len(words) <= max_words:
        return text, ""

    opening = " ".join(words[:max_words])
    continuation = " ".join(words[max_words:])

    return opening, continuation


def _is_promo_fragment(value: str) -> bool:
    if not value:
        return False

    normalized = re.sub(r"\s+", " ", value).strip(" -•—*")
    if not normalized:
        return False

    promo_patterns = (
        r"^Follow\b",
        r"^Also\s+Read\b",
        r"^Add\s+as\s+a\s+preferred\b",
        r"^Preferred\s+source\b",
        r"^source\s+on\b",
        r"^Us\s*:??$",
        r"^Read\s+More\b",
    )

    return any(
        re.match(pattern, normalized, flags=re.IGNORECASE)
        for pattern in promo_patterns
    ) or bool(
        re.search(
            r"\b(?:follow\s+us|also\s+read|add\s+as\s+a\s+preferred|preferred\s+source|source\s+on\s+google)\b",
            normalized,
            flags=re.IGNORECASE,
        )
    )


def _remove_promo_fragments(body: str) -> str:
    lines = body.splitlines()
    cleaned_lines = []
    skip_next_nonempty = False

    for line in lines:
        stripped = line.strip()

        if not stripped:
            skip_next_nonempty = False
            cleaned_lines.append("")
            continue

        normalized = re.sub(r"\s+", " ", stripped).strip(" -•—*")
        if not normalized:
            continue

        if _is_promo_fragment(normalized):
            skip_next_nonempty = True
            continue

        if skip_next_nonempty:
            if len(normalized.split()) <= 8:
                skip_next_nonempty = False
                continue
            skip_next_nonempty = False

        cleaned_lines.append(stripped)

    body = "\n".join(cleaned_lines)
    body = re.sub(r"\n{3,}", "\n\n", body)
    return body.strip()


def clean_article_body(body: str) -> str:

    if not body:
        return ""

    body = str(body)

    body = body.replace("\r\n", "\n").replace("\r", "\n")

    # Remove URLs.
    body = re.sub(
        r"https?://\S+",
        "",
        body,
        flags=re.IGNORECASE,
    )

    # Remove source attribution.
    body = re.sub(
        r"(?im)^\s*(?:మూల వార్త|Original report)\s*:?.*$",
        "",
        body,
    )

    body = _remove_promo_fragments(body)

    cleaned_lines = []

    for line in body.splitlines():

        stripped = line.strip()

        if not stripped:
            cleaned_lines.append("")
            continue

        if re.match(
            r"^(?:Follow\s+Us|Also\s+Read|Read\s+More|Follow)\s*:?\s*$",
            stripped,
            flags=re.IGNORECASE,
        ):
            continue

        if stripped in {"-", "–", "—", "•"}:
            continue

        if re.match(
            r"^(?:Add\s+as\s+a\s+preferred|Preferred\s+source)",
            stripped,
            flags=re.IGNORECASE,
        ):
            continue

        cleaned_lines.append(stripped)

    body = "\n".join(cleaned_lines)

    # Remove excessive spaces without damaging newlines.
    body = re.sub(r"[ \t]+", " ", body)

    # Remove excessive blank lines.
    body = re.sub(r"\n{3,}", "\n\n", body)

    body = _remove_repeated_sentences(body)

    return body.strip()


def _remove_repeated_sentences(body: str) -> str:
    seen = set()
    paragraphs = []

    for paragraph in re.split(r"\n\s*\n", body):
        paragraph = re.sub(r"రూ\.\s", "రూ\ue000 ", paragraph.strip())
        parts = re.split(
            r"(?<=[.!?।])(\s+)",
            paragraph,
        )
        unique_parts = []
        pending_separator = ""

        for index in range(0, len(parts), 2):
            sentence = re.sub(
                r"\s+",
                " ",
                parts[index].replace("\ue000", "."),
            ).strip()
            separator = parts[index + 1] if index + 1 < len(parts) else ""
            normalized = "".join(
                char.casefold() for char in sentence if char.isalnum()
            )

            if len(normalized) >= 25 and normalized in seen:
                pending_separator += separator
                continue

            if len(normalized) >= 25:
                seen.add(normalized)
            if unique_parts:
                if "\n\n" in pending_separator:
                    unique_parts.append("\n\n")
                elif "\n" in pending_separator:
                    unique_parts.append("\n")
                else:
                    unique_parts.append(" ")
            unique_parts.append(sentence)
            pending_separator = separator

        if unique_parts:
            paragraphs.append("".join(unique_parts))

    return "\n\n".join(paragraphs)


def get_article_body(article) -> str:

    telugu_body = (
        getattr(article, "body_te", None) or ""
    ).strip()

    if TELUGU_CHAR_RE.search(telugu_body):
        body = telugu_body

    else:
        legacy_body = (
            getattr(article, "body_en", None) or ""
        ).strip()

        body = (
            legacy_body
            if TELUGU_CHAR_RE.search(legacy_body)
            else ""
        )

    body = clean_article_body(body)

    if not contains_telugu_script(body):
        return ""

    return body


# =========================================================
# DUPLICATE HEADLINE REMOVAL
# =========================================================

def remove_duplicate_title(body: str, title: str) -> str:
    """
    Remove a repeated headline from the beginning of the body.

    Handles:
    - Exact headline matches.
    - Different whitespace.
    - Punctuation differences.
    - Headline and body text on the same first line.
    """

    if not body or not title:
        return body or ""

    lines = body.splitlines()

    while lines and not lines[0].strip():
        lines.pop(0)

    if not lines:
        return ""

    # Ignore punctuation and spaces while comparing.
    title_characters = [
        char for char in title
        if char.isalnum()
    ]

    if not title_characters:
        return "\n".join(lines).strip()

    headline_pattern = (
        r"^\s*"
        + r"[\s\W_]*".join(
            re.escape(char) for char in title_characters
        )
        + r"[\s\W_]*"
    )

    first_line = lines[0]

    match = re.match(
        headline_pattern,
        first_line,
        flags=re.UNICODE,
    )

    if match:
        remainder = first_line[match.end():].strip()

        if remainder:
            lines[0] = remainder
        else:
            lines.pop(0)

    return "\n".join(lines).strip()


# =========================================================
# ARTICLE QUERIES
# =========================================================

def get_published_articles():

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

    prepared = []

    for article in articles:

        if getattr(article, "status", None) != "published":
            continue

        if not get_article_title(article):
            continue

        if not get_article_body(article):
            continue

        prepared.append(article)

    return prepared


# =========================================================
# IMAGE HANDLING
# =========================================================

class ContainedImage(Flowable):

    def __init__(self, image_buffer, width, height):

        super().__init__()

        self.image = ImageReader(image_buffer)

        self.image_width, self.image_height = self.image.getSize()

        self.width = width
        self.height = height

    def draw(self):

        scale = min(
            self.width / self.image_width,
            self.height / self.image_height,
        )

        draw_width = self.image_width * scale
        draw_height = self.image_height * scale

        self.canv.drawImage(
            self.image,
            (self.width - draw_width) / 2,
            (self.height - draw_height) / 2,
            width=draw_width,
            height=draw_height,
            mask="auto",
        )


def download_article_image(image_url: str):

    if not image_url:
        return None

    try:

        parsed = urlparse(image_url)

        if parsed.scheme not in ("http", "https"):
            return None

        if not parsed.netloc:
            return None

        with requests.get(
            image_url,
            timeout=10,
            stream=True,
            headers={"User-Agent": "VSTV6DigitalMedia/1.0"},
        ) as response:

            response.raise_for_status()

            content_type = response.headers.get(
                "Content-Type",
                "",
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

            if total == 0:
                return None

            buffer.seek(0)

            return buffer

    except (requests.RequestException, ValueError):

        logger.warning(
            "Could not download article image: %s",
            image_url,
        )

        return None


def _article_image(article, width, height=None):

    image_url = getattr(article, "image_url", None)

    image_buffer = download_article_image(image_url)

    if image_buffer is None:
        return None

    height = height or width * 0.62

    try:

        return ContainedImage(
            image_buffer,
            width,
            height,
        )

    except Exception:

        logger.exception(
            "Could not prepare image for article %s",
            getattr(article, "id", "unknown"),
        )

        return None


# =========================================================
# ARTICLE LAYOUT HELPERS
# =========================================================

def make_headline_rule(width):

    rule = Table(
        [[""]],
        colWidths=[width],
        rowHeights=[0.7 * mm],
    )

    rule.setStyle(
        TableStyle(
            [
                (
                    "BACKGROUND",
                    (0, 0),
                    (-1, -1),
                    colors.HexColor("#B51F36"),
                ),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )

    return rule


def make_article_intro(article, styles, column_width):

    title_text = escape_pdf_text(get_article_title(article))

    title = Paragraph(
        title_text,
        styles["NewsHeadline"],
    )

    image_width = column_width - 4 * mm

    intro = [
        title,
        make_headline_rule(image_width),
        Spacer(1, 1.5 * mm),
    ]

    image = _article_image(
        article,
        image_width,
        height=36 * mm,
    )

    if image:
        intro.extend(
            [
                image,
                Spacer(1, 1.5 * mm),
            ]
        )

    return intro


def make_article_separator(column_width):

    separator = Table(
        [[""]],
        colWidths=[column_width - 4 * mm],
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

    return separator


def make_paragraphs(body, styles):

    if not body:
        return []

    body = clean_article_body(body)

    if not body:
        return []

    body = body.replace("\r\n", "\n").replace("\r", "\n")
    body = re.sub(r"\n{3,}", "\n\n", body)

    paragraphs = re.split(r"\n\s*\n", body)

    result = []

    for paragraph in paragraphs:

        paragraph = paragraph.strip()

        if not paragraph:
            continue

        paragraph = re.sub(r"[ \t]+", " ", paragraph)

        result.append(
            Paragraph(
                escape_pdf_text(paragraph),
                styles["NewsBody"],
            )
        )

    return result


# =========================================================
# PAGE HEADER
# =========================================================

def draw_interior_header(canvas, doc):

    canvas.saveState()

    canvas.setFont("Helvetica-Bold", 8)

    canvas.setFillColor(
        colors.HexColor("#142D4E")
    )

    canvas.drawString(
        MARGIN,
        PAGE_HEIGHT - 7 * mm,
        "VSTV6 DIGITAL MEDIA",
    )

    canvas.setFont("Helvetica", 8)

    canvas.setFillColor(
        colors.HexColor("#657185")
    )

    canvas.drawRightString(
        PAGE_WIDTH - MARGIN,
        PAGE_HEIGHT - 7 * mm,
        doc.edition_date,
    )

    canvas.setStrokeColor(
        colors.HexColor("#C8D1DC")
    )

    canvas.setLineWidth(0.55)

    canvas.line(
        MARGIN,
        PAGE_HEIGHT - HEADER_HEIGHT,
        PAGE_WIDTH - MARGIN,
        PAGE_HEIGHT - HEADER_HEIGHT,
    )

    canvas.restoreState()


# =========================================================
# PAGE FOOTER
# =========================================================

class NewspaperCanvas(reportlab_canvas.Canvas):
    """Buffer pages and print correct page numbers."""

    def __init__(self, *args, **kwargs):

        super().__init__(*args, **kwargs)

        self.saved_page_states = []

    def showPage(self):

        self.saved_page_states.append(
            dict(self.__dict__)
        )

        self._startPage()

    def save(self):

        total_pages = len(self.saved_page_states)

        for page_number, state in enumerate(
            self.saved_page_states,
            start=1,
        ):

            self.__dict__.update(state)

            self.saveState()

            self.setStrokeColor(
                colors.HexColor("#BCCCDC")
            )

            self.setLineWidth(0.6)

            self.line(
                MARGIN,
                FOOTER_HEIGHT,
                PAGE_WIDTH - MARGIN,
                FOOTER_HEIGHT,
            )

            self.setFont(
                "VSTV6Telugu",
                8,
            )

            self.setFillColor(
                colors.HexColor("#52606D")
            )

            self.drawString(
                MARGIN,
                5 * mm,
                "తెలుగు వార్తా పత్రిక",
            )

            self.setFont("Helvetica", 8)

            self.drawRightString(
                PAGE_WIDTH - MARGIN,
                5 * mm,
                f"Page {page_number} of {total_pages}",
            )

            self.restoreState()

            reportlab_canvas.Canvas.showPage(self)

        reportlab_canvas.Canvas.save(self)


# =========================================================
# FRONT PAGE HELPERS
# =========================================================

def make_lead_kicker(styles, content_width):

    kicker = Table(
        [[
            Paragraph(
                "ప్రధాన వార్త  |  TOP STORY",
                styles["NewsKicker"],
            )
        ]],
        colWidths=[content_width],
        rowHeights=[6 * mm],
    )

    kicker.setStyle(
        TableStyle(
            [
                (
                    "BACKGROUND",
                    (0, 0),
                    (-1, -1),
                    colors.HexColor("#B51F36"),
                ),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 3 * mm),
                ("RIGHTPADDING", (0, 0), (-1, -1), 3 * mm),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )

    return kicker


def make_lead_headline(article, title_text, content_width, styles):

    image_width = 62 * mm

    lead_image = _article_image(
        article,
        image_width,
        height=40 * mm,
    )

    headline_width = (
        content_width
        - image_width
        - 8 * mm
    )

    lead_cells = [
        Paragraph(
            title_text,
            styles["NewsLeadHeadline"],
        ),
        lead_image or "",
    ]

    lead_headline = Table(
        [lead_cells],
        colWidths=[
            headline_width,
            image_width + 4 * mm,
        ],
    )

    lead_headline.setStyle(
        TableStyle(
            [
                (
                    "BACKGROUND",
                    (0, 0),
                    (0, 0),
                    colors.HexColor("#F2F5F8"),
                ),
                (
                    "LINEBEFORE",
                    (0, 0),
                    (0, 0),
                    2.5,
                    colors.HexColor("#B51F36"),
                ),
                (
                    "BOX",
                    (0, 0),
                    (-1, -1),
                    0.6,
                    colors.HexColor("#D7DEE7"),
                ),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (0, 0), 3 * mm),
                ("RIGHTPADDING", (0, 0), (-1, -1), 2 * mm),
                ("LEFTPADDING", (1, 0), (1, 0), 2 * mm),
                ("TOPPADDING", (0, 0), (-1, -1), 2 * mm),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 2 * mm),
            ]
        )
    )

    return lead_headline


# =========================================================
# NEWSPAPER PDF GENERATOR
# =========================================================

def generate_newspaper_pdf(
    articles=None,
    edition_date=None,
):
    """
    Generate a Telugu newspaper PDF.

    Selected published articles are preserved.
    There is no fixed page limit.

    Returns:
        io.BytesIO
    """

    register_newspaper_fonts()

    # Use selected articles when supplied.
    if articles is None:
        articles = get_published_articles()

    articles = prepare_articles(articles)

    if not articles:

        raise ValueError(
            "No selected published Telugu articles "
            "with complete body text were found."
        )

    edition_date_text = format_date(edition_date)

    output = io.BytesIO()

    content_width = PAGE_WIDTH - 2 * MARGIN

    column_width = (
        content_width - (COLUMN_COUNT - 1) * COLUMN_GAP
    ) / COLUMN_COUNT

    frame_bottom = FOOTER_HEIGHT

    masthead_top = PAGE_HEIGHT - MARGIN

    masthead_bottom = (
        masthead_top - MASTHEAD_HEIGHT
    )

    lead_bottom = (
        masthead_bottom - LEAD_HEIGHT
    )

    front_column_height = (
        lead_bottom - frame_bottom
    )

    interior_height = (
        PAGE_HEIGHT
        - MARGIN
        - HEADER_HEIGHT
        - frame_bottom
    )

    # -----------------------------------------------------
    # COLUMN FRAMES
    # -----------------------------------------------------

    def make_columns(height):

        frames = []

        for index in range(COLUMN_COUNT):

            x_position = (
                MARGIN
                + index * (column_width + COLUMN_GAP)
            )

            frames.append(
                Frame(
                    x_position,
                    FOOTER_HEIGHT,
                    column_width,
                    height,
                    id=f"newspaper-column-{index + 1}",
                    leftPadding=1 * mm,
                    rightPadding=1 * mm,
                    topPadding=1 * mm,
                    bottomPadding=1 * mm,
                )
            )

        return frames

    # -----------------------------------------------------
    # DOCUMENT
    # -----------------------------------------------------

    doc = BaseDocTemplate(
        output,
        pagesize=A4,
        rightMargin=MARGIN,
        leftMargin=MARGIN,
        topMargin=MARGIN + HEADER_HEIGHT,
        bottomMargin=frame_bottom,
        title="VSTV6 Digital Media - Telugu Newspaper",
        author="VSTV6 Digital Media",
        allowSplitting=1,
    )

    doc.edition_date = edition_date_text

    # -----------------------------------------------------
    # MASTHEAD FRAME
    # -----------------------------------------------------

    masthead_frame = Frame(
        MARGIN,
        masthead_bottom,
        content_width,
        MASTHEAD_HEIGHT,
        id="newspaper-masthead",
        leftPadding=0,
        rightPadding=0,
        topPadding=0,
        bottomPadding=0,
    )

    # -----------------------------------------------------
    # LEAD STORY FRAME
    # -----------------------------------------------------

    lead_frame = Frame(
        MARGIN,
        lead_bottom,
        content_width,
        LEAD_HEIGHT,
        id="newspaper-lead",
        leftPadding=2 * mm,
        rightPadding=2 * mm,
        topPadding=2 * mm,
        bottomPadding=2 * mm,
    )

    # -----------------------------------------------------
    # PAGE TEMPLATES
    # -----------------------------------------------------

    doc.addPageTemplates(
        [
            PageTemplate(
                id="front-page",
                frames=[
                    masthead_frame,
                    lead_frame,
                    *make_columns(front_column_height),
                ],
            ),
            PageTemplate(
                id="interior",
                frames=make_columns(interior_height),
                onPage=draw_interior_header,
            ),
        ]
    )

    styles = get_styles()

    story = []

    # =====================================================
    # FRONT PAGE MASTHEAD
    # =====================================================

    if not MASTHEAD_IMAGE_PATH.is_file():

        raise FileNotFoundError(
            f"Newspaper masthead image not found: "
            f"{MASTHEAD_IMAGE_PATH}"
        )

    masthead_image = Image(
        str(MASTHEAD_IMAGE_PATH),
        width=content_width,
        height=40 * mm,
        kind="proportional",
    )

    story.append(masthead_image)

    edition_bar = Table(
        [
            [
                Paragraph(
                    "తేదీ: " + escape_pdf_text(edition_date_text),
                    styles["NewsEdition"],
                ),
                Paragraph(
                    "VSTV6 Digital Media · Telangana",
                    styles["NewsEdition"],
                ),
                Paragraph(
                    "వార్తలు · విశేషాలు · ప్రజల గొంతుక",
                    styles["NewsEdition"],
                ),
            ]
        ],
        colWidths=[content_width / 3] * 3,
    )

    edition_bar.setStyle(
        TableStyle(
            [
                (
                    "BACKGROUND",
                    (0, 0),
                    (-1, -1),
                    colors.HexColor("#F0F3F7"),
                ),
                (
                    "LINEABOVE",
                    (0, 0),
                    (-1, -1),
                    0.6,
                    colors.HexColor("#C8D1DC"),
                ),
                (
                    "LINEBELOW",
                    (0, 0),
                    (-1, -1),
                    0.6,
                    colors.HexColor("#C8D1DC"),
                ),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("LEFTPADDING", (0, 0), (-1, -1), 2 * mm),
                ("RIGHTPADDING", (0, 0), (-1, -1), 2 * mm),
                ("TOPPADDING", (0, 0), (-1, -1), 1.2 * mm),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 1.2 * mm),
            ]
        )
    )

    story.append(edition_bar)

    story.append(Spacer(1, 2 * mm))

    # Move from masthead to lead story.
    story.append(FrameBreak())

    # =====================================================
    # ARTICLES
    # =====================================================

    printed_articles = 0

    for article in articles:

        body = get_article_body(article)
        title = get_article_title(article)

        if not body or not title:
            continue

        # Remove repeated headline from article body.
        body = remove_duplicate_title(body, title)

        if not body.strip():
            continue

        # Convert body into paragraphs once.
        paragraphs = make_paragraphs(body, styles)

        if not paragraphs:
            continue

        title_text = escape_pdf_text(title)

        # -------------------------------------------------
        # LEAD STORY
        # -------------------------------------------------

        if printed_articles == 0:

            kicker = make_lead_kicker(
                styles,
                content_width,
            )

            lead_headline = make_lead_headline(
                article,
                title_text,
                content_width,
                styles,
            )

            story.extend(
                [
                    kicker,
                    Spacer(1, 1.5 * mm),
                    lead_headline,
                ]
            )

            # Move to the first article column.
            story.append(FrameBreak())

            # Interior template starts on the next page.
            story.append(NextPageTemplate("interior"))

            # Lead story body flows into the first column.
            for paragraph in paragraphs:
                story.append(paragraph)

        # -------------------------------------------------
        # INTERIOR ARTICLES
        # -------------------------------------------------

        else:

            intro = make_article_intro(
                article,
                styles,
                column_width,
            )

            # Keep the headline, image and opening
            # paragraph together.
            first_paragraph = paragraphs[0]

            story.append(
                KeepTogether(
                    [
                        *intro,
                        first_paragraph,
                    ]
                )
            )

            # Remaining paragraphs flow naturally through
            # the columns and subsequent pages.
            for paragraph in paragraphs[1:]:
                story.append(paragraph)

        # -------------------------------------------------
        # ARTICLE SEPARATOR
        # -------------------------------------------------

        story.append(
            Spacer(1, 1.5 * mm)
        )

        story.append(
            make_article_separator(column_width)
        )

        story.append(
            Spacer(1, 2 * mm)
        )

        printed_articles += 1

    # =====================================================
    # VALIDATION
    # =====================================================

    if printed_articles == 0:

        raise ValueError(
            "No Telugu article bodies are available to print."
        )

    logger.info(
        "Generating newspaper with %s selected articles",
        printed_articles,
    )

    # =====================================================
    # BUILD PDF
    # =====================================================

    try:

        doc.build(
            story,
            canvasmaker=NewspaperCanvas,
        )

    except Exception:

        logger.exception(
            "Failed to generate VSTV6 newspaper PDF"
        )

        raise

    output.seek(0)

    return output


# =========================================================
# ROUTE-COMPATIBLE FUNCTION
# =========================================================

def create_newspaper_pdf(
    articles,
    edition_date=None,
):
    """Compatible with routes/newspaper.py."""

    return generate_newspaper_pdf(
        articles=articles,
        edition_date=edition_date,
    )