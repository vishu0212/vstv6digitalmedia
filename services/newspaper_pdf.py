from datetime import datetime
from io import BytesIO
from pathlib import Path
import re
from xml.sax.saxutils import escape

from flask import current_app
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.pagesizes import A3, portrait
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Image,
    Table,
    TableStyle,
    KeepTogether,
)

# =========================================================
# VSTV6 DIGITAL MEDIA — COMPACT NEWSPAPER PDF
# =========================================================

NAVY = colors.HexColor("#082B63")
DARK_NAVY = colors.HexColor("#061D40")
RED = colors.HexColor("#D71920")
INK = colors.HexColor("#20242B")
MUTED = colors.HexColor("#626B78")
LIGHT_GREY = colors.HexColor("#DDE3EB")
PAPER = colors.white

PAGE_SIZE = portrait(A3)
PAGE_WIDTH, PAGE_HEIGHT = PAGE_SIZE
LEFT_MARGIN = 10 * mm
RIGHT_MARGIN = 10 * mm
TOP_MARGIN = 8 * mm
BOTTOM_MARGIN = 14 * mm
CONTENT_WIDTH = PAGE_WIDTH - LEFT_MARGIN - RIGHT_MARGIN
GUTTER = 5 * mm
COLUMN_WIDTH = (CONTENT_WIDTH - GUTTER) / 2


def _register_telugu_font():
    """Register an available Telugu-capable Windows font."""
    candidates = [
        Path(r"C:\Windows\Fonts\Nirmala.ttf"),
        Path(r"C:\Windows\Fonts\Nirmala.ttc"),
        Path(r"C:\Windows\Fonts\Gautami.ttf"),
    ]

    for font_path in candidates:
        if not font_path.is_file():
            continue
        try:
            if font_path.suffix.lower() == ".ttc":
                pdfmetrics.registerFont(
                    TTFont("VSTV6Telugu", str(font_path), subfontIndex=0)
                )
            else:
                pdfmetrics.registerFont(TTFont("VSTV6Telugu", str(font_path)))
            return "VSTV6Telugu"
        except Exception:
            continue

    return "Helvetica"


def _clean(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _safe(value):
    return escape(_clean(value))


def _local_article_image(image_url):
    """Only use local files under Flask's static folder."""
    image_url = _clean(image_url)
    if not image_url.startswith("/static/"):
        return None

    relative_path = image_url[len("/static/"):]
    if not relative_path:
        return None

    static_root = Path(current_app.static_folder).resolve()
    image_path = (static_root / relative_path).resolve()

    try:
        image_path.relative_to(static_root)
    except ValueError:
        return None

    return image_path if image_path.is_file() else None


def _scaled_image(path, max_width, max_height):
    if not path:
        return None
    try:
        img = Image(str(path))
        scale = min(max_width / img.imageWidth, max_height / img.imageHeight)
        img.drawWidth = img.imageWidth * scale
        img.drawHeight = img.imageHeight * scale
        img.hAlign = "CENTER"
        return img
    except Exception:
        return None


def _article_fields(article):
    title = (
        getattr(article, "title_te", None)
        or getattr(article, "title_en", None)
        or "VSTV6 News"
    )
    summary = (
        getattr(article, "summary_te", None)
        or getattr(article, "summary_en", None)
        or getattr(article, "body_te", None)
        or getattr(article, "body_en", None)
        or "వివరాలు త్వరలో అందుబాటులో ఉంటాయి."
    )
    category = getattr(article, "category", None)
    category_name = (
        getattr(category, "name_te", None)
        or getattr(category, "name_en", None)
        or "తెలంగాణ"
    )
    return title, summary, category_name


def create_newspaper_pdf(articles, edition_date=None):
    """Build a professional A3 newspaper PDF and return it as BytesIO."""
    output = BytesIO()
    today = datetime.now().date()

    try:
        parsed = datetime.strptime(edition_date or today.isoformat(), "%Y-%m-%d")
        formatted_date = parsed.strftime("%d %B %Y")
    except (TypeError, ValueError):
        formatted_date = today.strftime("%d %B %Y")

    font_name = _register_telugu_font()
    doc = SimpleDocTemplate(
        output,
        pagesize=PAGE_SIZE,
        leftMargin=LEFT_MARGIN,
        rightMargin=RIGHT_MARGIN,
        topMargin=TOP_MARGIN,
        bottomMargin=BOTTOM_MARGIN,
        title=f"VSTV6 Digital Media Newspaper - {formatted_date}",
        author="VSTV6 Digital Media",
        subject="Telangana Telugu and English News",
    )

    styles = getSampleStyleSheet()

    masthead_style = ParagraphStyle(
        "VSTV6Masthead",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=25,
        leading=29,
        textColor=RED,
        alignment=TA_CENTER,
        spaceAfter=1.5 * mm,
    )
    tagline_style = ParagraphStyle(
        "VSTV6Tagline",
        parent=styles["Normal"],
        fontName=font_name,
        fontSize=9,
        leading=13,
        textColor=INK,
        alignment=TA_CENTER,
        spaceAfter=1.5 * mm,
    )
    section_style = ParagraphStyle(
        "VSTV6Section",
        parent=styles["Heading2"],
        fontName=font_name,
        fontSize=13,
        leading=18,
        textColor=NAVY,
        alignment=TA_LEFT,
        spaceBefore=1 * mm,
        spaceAfter=2.5 * mm,
    )
    lead_title_style = ParagraphStyle(
        "VSTV6LeadTitle",
        parent=styles["Heading1"],
        fontName=font_name,
        fontSize=16,
        leading=22,
        textColor=DARK_NAVY,
        alignment=TA_LEFT,
        spaceAfter=2 * mm,
        wordWrap="CJK",
    )
    article_title_style = ParagraphStyle(
        "VSTV6ArticleTitle",
        parent=styles["Heading2"],
        fontName=font_name,
        fontSize=11,
        leading=15,
        textColor=INK,
        alignment=TA_LEFT,
        spaceAfter=1.5 * mm,
        wordWrap="CJK",
    )
    body_style = ParagraphStyle(
        "VSTV6ArticleBody",
        parent=styles["BodyText"],
        fontName=font_name,
        fontSize=8,
        leading=11,
        textColor=colors.HexColor("#343A43"),
        alignment=TA_LEFT,
        spaceAfter=1.5 * mm,
        wordWrap="CJK",
    )
    category_style = ParagraphStyle(
        "VSTV6Category",
        parent=styles["Normal"],
        fontName=font_name,
        fontSize=8,
        leading=11,
        textColor=RED,
        alignment=TA_LEFT,
        spaceAfter=1 * mm,
        wordWrap="CJK",
    )
    small_style = ParagraphStyle(
        "VSTV6Small",
        parent=styles["Normal"],
        fontName=font_name,
        fontSize=7,
        leading=9,
        textColor=MUTED,
        alignment=TA_LEFT,
        wordWrap="CJK",
    )
    info_style = ParagraphStyle(
        "VSTV6EditionInfo",
        parent=styles["Normal"],
        fontName=font_name,
        fontSize=8,
        leading=11,
        textColor=PAPER,
        alignment=TA_CENTER,
        wordWrap="CJK",
    )

    story = []

    # Compact masthead banner. It is deliberately placed before the edition bar.
    header_path = (
        Path(current_app.static_folder) / "images" / "vstv6-newspaper-header.png"
    )
    header = _scaled_image(
        header_path if header_path.is_file() else None,
        max_width=CONTENT_WIDTH,
        max_height=PAGE_HEIGHT,
    )
    if header:
        story.append(header)
        story.append(Spacer(1, 2 * mm))
    else:
        story.append(Paragraph("VSTV6 DIGITAL MEDIA", masthead_style))
        story.append(
            Paragraph(
                "ప్రజల స్వరం .. ప్రజల కోసం .. ఎప్పుడూ మీతో ..",
                tagline_style,
            )
        )
        story.append(
            Paragraph(
                "తెలంగాణ వార్తలు | తెలుగు &amp; English | స్థానికం | జాతీయం",
                tagline_style,
            )
        )

    # Edition bar: explicit white text on navy background.
    edition_table = Table(
        [[
            Paragraph(f"<b>{_safe(formatted_date)}</b>", info_style),
            Paragraph("<b>VSTV6 DIGITAL MEDIA</b><br/>Telangana First", info_style),
            Paragraph("తెలంగాణ వార్తలు<br/>తెలుగు &amp; English", info_style),
        ]],
        colWidths=[
            CONTENT_WIDTH * 0.25,
            CONTENT_WIDTH * 0.45,
            CONTENT_WIDTH * 0.30,
        ],
    )
    edition_table.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), NAVY),
        ("TEXTCOLOR", (0, 0), (-1, -1), PAPER),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LINEBELOW", (0, 0), (-1, -1), 2, RED),
    ]))
    story.append(edition_table)
    story.append(Spacer(1, 3 * mm))

    if not articles:
        story.append(Paragraph("No articles were selected for this edition.", body_style))
    else:
        story.append(
            Paragraph("నేటి ముఖ్య వార్తలు | TODAY'S TOP STORIES", section_style)
        )

        # Lead story: full-width headline, optional compact image and summary.
        lead = articles[0]
        title, summary, category_name = _article_fields(lead)
        lead_text = [
            Paragraph(f"<b>{_safe(category_name)}</b>", category_style),
            Paragraph(_safe(title), lead_title_style),
            Paragraph(_safe(summary), body_style),
        ]
        lead_source = _clean(getattr(lead, "source_name", None))
        if lead_source:
            lead_text.append(
                Paragraph(f"Source: {_safe(lead_source)}", small_style)
            )

        lead_image_path = _local_article_image(getattr(lead, "image_url", None))
        lead_image = _scaled_image(
            lead_image_path,
            max_width=75 * mm,
            max_height=43 * mm,
        )
        if lead_image:
            lead_content = Table(
                [[lead_image, lead_text]],
                colWidths=[80 * mm, CONTENT_WIDTH - 80 * mm],
            )
            lead_content.setStyle(TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]))
        else:
            lead_content = Table([[lead_text]], colWidths=[CONTENT_WIDTH - 4 * mm])
            lead_content.setStyle(TableStyle([
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ]))

        lead_card = Table([[lead_content]], colWidths=[CONTENT_WIDTH])
        lead_card.setStyle(TableStyle([
            ("BOX", (0, 0), (-1, -1), 0.6, LIGHT_GREY),
            ("LINEABOVE", (0, 0), (-1, 0), 2, RED),
            ("BACKGROUND", (0, 0), (-1, -1), PAPER),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 3),
            ("RIGHTPADDING", (0, 0), (-1, -1), 3),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        story.append(KeepTogether([lead_card, Spacer(1, 3 * mm)]))

        # Remaining stories: vertical portrait newspaper flow.
        # Full-width cards avoid unbreakable table rows and LayoutError.
        remaining = list(articles[1:])
        if remaining:
            story.append(
                Paragraph("మరిన్ని వార్తలు | MORE NEWS", section_style)
            )

            for article in remaining:
                title, summary, category_name = _article_fields(article)

                article_items = [
                    Paragraph(f"<b>{_safe(category_name)}</b>", category_style),
                    Paragraph(_safe(title), article_title_style),
                ]

                image_path = _local_article_image(
                    getattr(article, "image_url", None)
                )
                article_image = _scaled_image(
                    image_path,
                    max_width=52 * mm,
                    max_height=32 * mm,
                )

                summary_para = Paragraph(_safe(summary), body_style)
                if article_image:
                    text_items = [summary_para]
                    source_name = _clean(getattr(article, "source_name", None))
                    if source_name:
                        text_items.append(
                            Paragraph(f"Source: {_safe(source_name)}", small_style)
                        )

                    row = Table(
                        [[article_image, text_items]],
                        colWidths=[57 * mm, CONTENT_WIDTH - 65 * mm],
                        hAlign="LEFT",
                    )
                    row.setStyle(TableStyle([
                        ("VALIGN", (0, 0), (-1, -1), "TOP"),
                        ("LEFTPADDING", (0, 0), (-1, -1), 4),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                        ("TOPPADDING", (0, 0), (-1, -1), 3),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                    ]))
                    article_items.append(row)
                else:
                    article_items.append(summary_para)
                    source_name = _clean(getattr(article, "source_name", None))
                    if source_name:
                        article_items.append(
                            Paragraph(f"Source: {_safe(source_name)}", small_style)
                        )

                card = Table(
                    [[article_items]],
                    colWidths=[CONTENT_WIDTH],
                    hAlign="LEFT",
                )
                card.setStyle(TableStyle([
                    ("BOX", (0, 0), (-1, -1), 0.5, LIGHT_GREY),
                    ("LINEABOVE", (0, 0), (-1, 0), 1.3, NAVY),
                    ("BACKGROUND", (0, 0), (-1, -1), PAPER),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (-1, -1), 6),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 6),
                    ("TOPPADDING", (0, 0), (-1, -1), 5),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ]))

                story.append(card)
                story.append(Spacer(1, 2 * mm))

    def draw_page_footer(canvas, document):
        canvas.saveState()
        canvas.setStrokeColor(RED)
        canvas.setLineWidth(1)
        canvas.line(
            document.leftMargin,
            10 * mm,
            PAGE_WIDTH - document.rightMargin,
            10 * mm,
        )
        canvas.setFont("Helvetica-Bold", 8)
        canvas.setFillColor(NAVY)
        canvas.drawString(
            document.leftMargin,
            5 * mm,
            "VSTV6 Digital Media | Telangana First",
        )
        canvas.drawRightString(
            PAGE_WIDTH - document.rightMargin,
            5 * mm,
            f"Page {document.page}",
        )
        canvas.restoreState()

    doc.build(
        story,
        onFirstPage=draw_page_footer,
        onLaterPages=draw_page_footer,
    )
    output.seek(0)
    return output
