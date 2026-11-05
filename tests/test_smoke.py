import os
import pytest
from types import SimpleNamespace

@pytest.fixture()
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("SECRET_KEY", "test-secret-only")
    monkeypatch.setenv("DATABASE_URL", "sqlite:///" + str(tmp_path / "test.db"))
    from app import create_app
    from extensions import db
    app = create_app()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    with app.app_context():
        db.create_all()
        yield app
        db.session.remove()
        db.drop_all()

def test_home(app):
    assert app.test_client().get("/").status_code == 200

def test_sitemap(app):
    response = app.test_client().get("/sitemap.xml")
    assert response.status_code == 200
    assert b"urlset" in response.data

def test_login(app):
    assert app.test_client().get("/auth/login").status_code == 200

def test_detect_language_uses_telugu_article_body():
    from services.news_collector import detect_language

    assert detect_language(
        title="English headline",
        summary="English summary",
        body="తెలుగు వార్తా కథనం",
    ) == "te"

def test_news_category_classification_uses_specific_context(app):
    from extensions import db
    from models import Category
    from services.news_collector import classify_category

    categories = [
        ("World", "ప్రపంచం", "world"),
        ("Entertainment", "వినోదం", "entertainment"),
        ("National", "జాతీయం", "national"),
        ("Sports", "క్రీడలు", "sports"),
        ("Telangana", "తెలంగాణ", "telangana"),
    ]

    with app.app_context():
        db.session.add_all(
            Category(name_en=name, name_te=name_te, slug=slug)
            for name, name_te, slug in categories
        )
        db.session.flush()

        cases = [
            ("అమెరికా అధ్యక్షుడు కీలక ప్రకటన చేశారు", "World"),
            ("తెలుగు సినిమా ట్రైలర్ విడుదల", "Entertainment"),
            ("ప్రపంచం గురించి తాజా వార్త", "National"),
            ("కేంద్ర ప్రభుత్వం కొత్త నిర్ణయం", "National"),
            ("క్రికెట్ మ్యాచ్‌లో టీమిండియా విజయం", "Sports"),
            ("హైదరాబాద్‌లో తెలంగాణ ప్రభుత్వం కీలక ప్రకటన", "Telangana"),
        ]

        for title, expected_category in cases:
            category = classify_category(title)
            assert category is not None
            assert category.name_en == expected_category

def test_article_public_telugu_fields_hide_english_only_content():
    from models.article import Article

    article = Article(
        title_en="Telugu story",
        slug="telugu-story",
        summary_en="English summary",
        summary_te="English summary",
        body_en="English body",
        body_te="English body",
    )

    assert article.telugu_summary is None
    assert article.telugu_body is None
    article.summary_te = "తెలుగు వార్తా సారాంశం"
    article.body_te = "తెలుగు పూర్తి వార్త"

    assert article.telugu_summary == "తెలుగు వార్తా సారాంశం"
    assert article.telugu_body == "తెలుగు పూర్తి వార్త"

def test_telugu_news_includes_stories_containing_telugu_words():
    from models.article import Article, contains_telugu_script

    article = Article(
        title_en="Telugu story",
        title_te="తెలుగు headline",
        slug="mixed-story",
        summary_en="English summary",
        summary_te="తెలుగు summary",
        body_en="English body",
        body_te="తెలుగు పూర్తి కథనం with English content",
    )

    assert contains_telugu_script("తెలుగు వార్త with English")
    assert not contains_telugu_script("English-only article")
    assert article.telugu_title == "తెలుగు headline"
    assert article.telugu_summary is None
    assert article.telugu_body == "తెలుగు పూర్తి కథనం with English content"
    assert article.has_telugu_story

    article.title_te = "తెలుగు వార్త శీర్షిక"
    article.summary_te = "తెలుగు వార్తా సారాంశం"
    article.body_te = "తెలుగు పూర్తి వార్త."
    assert article.has_telugu_story
    assert article.telugu_summary == "తెలుగు వార్తా సారాంశం"

def test_public_news_pages_only_show_telugu_headline_and_body(
    tmp_path,
    monkeypatch,
):
    from datetime import datetime, timezone
    from urllib.parse import quote

    from app import create_app
    from config import Config
    from extensions import db
    from models import Article, Category, User

    monkeypatch.setenv("SECRET_KEY", "test-secret-only")
    database_url = "sqlite:///" + str(tmp_path / "news.db")
    monkeypatch.setenv("DATABASE_URL", database_url)
    monkeypatch.setattr(Config, "SQLALCHEMY_ENGINE_OPTIONS", {})
    monkeypatch.setattr(Config, "SQLALCHEMY_DATABASE_URI", database_url)
    app = create_app()

    with app.app_context():
        db.create_all()
        try:
            author = User(
                email="telugu-editor@example.com",
                display_name="తెలుగు సంపాదకుడు",
                password_hash="test-hash",
                role="editor",
            )
            category = Category(
                name_en="Telangana",
                name_te="తెలంగాణ",
                slug="telangana",
            )
            db.session.add_all([author, category])
            db.session.flush()

            valid_article = Article(
                title_en="Telugu story",
                title_te="తెలుగు వార్త శీర్షిక",
                slug="తెలుగు-వార్త-శీర్షిక",
                summary_en="English teaser",
                summary_te="తెలుగు వార్తా సారాంశం",
                body_en="English body",
                body_te="తెలుగు పూర్తి వార్త.",
                language="te",
                category_id=category.id,
                author_id=author.id,
                status="published",
                published_at=datetime.now(timezone.utc),
            )
            mixed_article = Article(
                title_en="Mixed story",
                title_te="తెలుగు headline",
                slug="mixed-story",
                summary_en="English teaser",
                summary_te="తెలుగు summary",
                body_en="English body",
                body_te="తెలుగు కథనం with English words.",
                language="te",
                category_id=category.id,
                author_id=author.id,
                status="published",
                published_at=datetime.now(timezone.utc),
            )
            db.session.add_all([valid_article, mixed_article])
            db.session.commit()
        finally:
            db.session.remove()

    client = app.test_client()
    home = client.get("/")
    assert home.status_code == 200
    assert "తెలుగు వార్త శీర్షిక".encode() in home.data
    assert "తెలుగు headline".encode() in home.data
    assert "English teaser".encode() not in home.data
    slug = "తెలుగు-వార్త-శీర్షిక"
    encoded_slug = quote(slug, safe="")
    assert client.get(f"/news/{encoded_slug}").status_code == 200
    assert client.get(f"/news/{quote(encoded_slug, safe='')}").status_code == 200
    mixed_detail = client.get("/news/mixed-story")
    assert mixed_detail.status_code == 200
    assert "తెలుగు కథనం with English words.".encode() in mixed_detail.data

    with app.app_context():
        db.drop_all()

def test_clean_article_body_preserves_paragraph_breaks():
    from services.news_collector import clean_article_body

    assert clean_article_body("మొదటి భాగం \r\n\r\n రెండో భాగం") == (
        "మొదటి భాగం\n\nరెండో భాగం"
    )

def test_newspaper_uses_telugu_legacy_body_and_ignores_english():
    from services.newspaper_pdf import get_article_body, prepare_articles

    legacy_telugu_article = SimpleNamespace(
        status="published",
        language="en",
        title_te="తెలుగు వార్త శీర్షిక",
        body_te=None,
        body_en="తెలుగు పూర్తి కథనం",
    )
    english_article = SimpleNamespace(
        status="published",
        language="en",
        title_te="తెలుగు వార్త శీర్షిక",
        body_te="An English body accidentally stored in the Telugu field",
        body_en="An English article",
    )

    assert get_article_body(legacy_telugu_article) == "తెలుగు పూర్తి కథనం"
    assert prepare_articles([legacy_telugu_article, english_article]) == [
        legacy_telugu_article
    ]

def test_newspaper_body_omits_source_link_line():
    from services.newspaper_pdf import get_article_body

    article = SimpleNamespace(
        body_te=(
            "తెలంగాణలో భారీ వర్షాలు కురిసే అవకాశం ఉంది.\n\n"
            "మూల వార్త: https://telugu.oneindia.com/news/telangana/story.html\n"
            "మరో పేరాలో లింక్ https://example.com ఉండకూడదు."
        ),
        body_en=None,
    )

    body = get_article_body(article)

    assert body == (
        "తెలంగాణలో భారీ వర్షాలు కురిసే అవకాశం ఉంది.\n\n"
        "మరో పేరాలో లింక్ ఉండకూడదు."
    )
    assert "https://" not in body

def test_newspaper_body_omits_publisher_promotions():
    from services.newspaper_pdf import get_article_body

    article = SimpleNamespace(
        body_te=(
            "తెలంగాణలో కొత్త ప్రాజెక్టు ప్రారంభం.\n\n"
            "- Follow Us :\n"
            "-\n\n"
            "Add as a preferred source on Google\n"
            "\nAlso Read ఈ కథనం గురించి మరిన్ని వివరాలు.\n\n"
            "ప్రాజెక్టు పనులు వచ్చే నెలలో ప్రారంభమవుతాయి."
        ),
        body_en=None,
    )

    body = get_article_body(article)

    assert body == (
        "తెలంగాణలో కొత్త ప్రాజెక్టు ప్రారంభం.\n\n"
        "ప్రాజెక్టు పనులు వచ్చే నెలలో ప్రారంభమవుతాయి."
    )
    assert "Follow Us" not in body
    assert "preferred source" not in body
    assert "Also Read" not in body

def test_newspaper_body_removes_repeated_gold_price_sentence():
    from services.newspaper_pdf import clean_article_body

    repeated_price = (
        "హైదరాబాద్‌లో 24 క్యారెట్ల బంగారం ధర గ్రాముకు రూ. 13,991గా ఉంది."
    )
    other_city = (
        "విజయవాడలో 24 క్యారెట్ల బంగారం ధర గ్రాముకు రూ. 13,991గా ఉంది."
    )
    body = clean_article_body(
        f"{repeated_price}\n\n{other_city}\n\n{repeated_price}"
    )

    assert body.count(repeated_price) == 1
    assert other_city in body

def test_newspaper_body_omits_google_promo_split_across_lines():
    from services.newspaper_pdf import get_article_body

    article = SimpleNamespace(
        body_te=(
            "తెలుగు వార్త మొదటి పేరా.\n"
            "\n-\n"
            "Add as a preferred\n"
            "source on google\n\n"
            "Also Read: పక్క కథనం శీర్షిక\n\n"
            "తెలుగు వార్త రెండో పేరా."
        ),
        body_en=None,
    )

    assert get_article_body(article) == (
        "తెలుగు వార్త మొదటి పేరా.\n\n"
        "తెలుగు వార్త రెండో పేరా."
    )

def test_newspaper_body_removes_multiline_promo_paragraphs():
    from services.newspaper_pdf import get_article_body

    article = SimpleNamespace(
        body_te=(
            "తెలుగు వార్త మొదటి పేరా.\n\n"
            "Follow\nUs :\n"
            "\nAdd as a preferred\nsource on Google\n\n"
            "Also Read\nసంబంధిత కథనం శీర్షిక\n\n"
            "తెలుగు వార్త చివరి పేరా."
        ),
        body_en=None,
    )

    body = get_article_body(article)

    assert body == (
        "తెలుగు వార్త మొదటి పేరా.\n\n"
        "తెలుగు వార్త చివరి పేరా."
    )

def test_newspaper_body_removes_promotions_without_blank_paragraphs():
    from services.newspaper_pdf import get_article_body

    article = SimpleNamespace(
        body_te=(
            "తెలుగు వార్త మొదటి పేరా.\n"
            "- Follow Us :\n"
            "-\n"
            "Add as a preferred\n"
            "source on google\n"
            "Also Read\n"
            "సంబంధిత కథనం శీర్షిక\n"
            "తెలుగు వార్త చివరి పేరా."
        ),
        body_en=None,
    )

    assert get_article_body(article) == (
        "తెలుగు వార్త మొదటి పేరా.\n"
        "తెలుగు వార్త చివరి పేరా."
    )

def test_newspaper_pdf_uses_justified_body_and_left_headline():
    from reportlab.lib.enums import TA_JUSTIFY, TA_LEFT
    from reportlab.lib.pagesizes import A4
    from services.newspaper_pdf import (
        COLUMN_COUNT,
        PAGE_HEIGHT,
        PAGE_WIDTH,
        MARGIN,
        COLUMN_GAP,
        TELUGU_BOLD_FONT_PATH,
        TELUGU_FONT_PATH,
        get_styles,
    )

    styles = get_styles()

    assert TELUGU_FONT_PATH.name == "NotoSerifTelugu-Regular.ttf"
    assert TELUGU_BOLD_FONT_PATH.name == "NotoSerifTelugu-Bold.ttf"
    assert styles["NewsBody"].alignment == TA_JUSTIFY
    assert styles["NewsBody"].fontSize == 9
    assert styles["NewsBody"].leading == 12
    assert styles["NewsBody"].fontName == "VSTV6Telugu"
    assert styles["NewsHeadline"].alignment == TA_LEFT
    assert styles["NewsHeadline"].fontSize == 13
    assert styles["NewsHeadline"].leading == 17
    assert styles["NewsLeadHeadline"].fontSize == 24
    assert styles["NewsLeadHeadline"].leading == 32
    assert styles["NewsSummary"].fontName == "VSTV6Telugu"
    assert styles["NewsSummary"].fontSize == 9
    assert styles["NewsSummary"].leading == 12
    assert styles["NewsEdition"].fontSize == 8
    assert styles["NewsKicker"].fontName == "VSTV6TeluguBold"
    assert COLUMN_COUNT == 2
    assert (PAGE_WIDTH, PAGE_HEIGHT) == A4
    assert MARGIN == pytest.approx(28.35, abs=0.1)
    assert COLUMN_GAP == pytest.approx(14.17, abs=0.1)


def test_newspaper_pdf_images_fit_medium_frames_without_cropping(monkeypatch):
    from io import BytesIO
    import services.newspaper_pdf as newspaper_pdf

    class ImageReaderStub:
        def __init__(self, _buffer):
            pass

        def getSize(self):
            return 200, 100

    class CanvasStub:
        def drawImage(self, image, x, y, width, height, mask):
            self.drawn = (image, x, y, width, height, mask)

    monkeypatch.setattr(newspaper_pdf, "ImageReader", ImageReaderStub)
    image = newspaper_pdf.ContainedImage(BytesIO(b"image"), 100, 40)
    image.canv = CanvasStub()

    image.draw()

    _, x, y, width, height, mask = image.canv.drawn
    assert (x, y, width, height) == pytest.approx((10, 0, 80, 40))
    assert mask == "auto"


def test_newspaper_pdf_uses_two_equal_columns():
    from services.newspaper_pdf import COLUMN_COUNT, COLUMN_GAP

    assert COLUMN_COUNT == 2
    assert COLUMN_GAP > 0


def test_newspaper_split_article_body_keeps_complete_copy():
    from services.newspaper_pdf import split_article_body

    body = ("తెలుగు వార్తా వాక్యం. " * 30).strip()
    opening, continuation = split_article_body(body, max_words=20)

    assert len(opening.split()) <= 20
    assert len((opening + " " + continuation).split()) == len(body.split())
    assert continuation

def test_newspaper_preview_renders_full_story_body(app, monkeypatch):
    import routes.newspaper as newspaper

    full_body = (
        "తెలుగు వార్త శీర్షిక\n\n"
        "తెలుగు మొదటి పేరా.\n\n"
        + ("తెలుగు పూర్తి కథనం. " * 20)
        + "చివరి వాక్యం."
    )
    article = SimpleNamespace(
        id=42,
        telugu_title="తెలుగు వార్త శీర్షిక",
        title_te="తెలుగు వార్త శీర్షిక",
        body_te=full_body,
        body_en=None,
        image_url=None,
        category=SimpleNamespace(name_te="తెలంగాణ", name_en="Telangana"),
    )
    second_article = SimpleNamespace(
        id=43,
        telugu_title="మరో తెలుగు వార్త",
        title_te="మరో తెలుగు వార్త",
        body_te="మరో వార్తా కథనం.",
        body_en=None,
        image_url=None,
        category=SimpleNamespace(name_te="జాతీయం", name_en="National"),
    )
    monkeypatch.setattr(newspaper, "_require_admin", lambda: None)
    monkeypatch.setattr(
        newspaper,
        "_get_selected_articles",
        lambda ids: [article, second_article],
    )

    with app.test_request_context(
        "/admin/newspaper/preview",
        method="POST",
        data={"article_ids": ["42"]},
    ):
        html = newspaper.preview.__wrapped__()

    assert "story-body" in html
    assert "తెలుగు మొదటి పేరా." in html
    assert "చివరి వాక్యం." in html
    assert "తెలుగు మొదటి పేరా.\n\nతెలుగు పూర్తి కథనం." in html
    assert html.count("తెలుగు వార్త శీర్షిక") == 1
    assert "size: A4 portrait" in html
    assert ".ticker," in html
    assert ".site-header,\n    .ticker," in html
    assert "margin: 0;" in html
    assert "width: 210mm;" in html
    assert "min-height: 297mm;" in html
    assert "padding: 10mm;" in html
    assert "height: 40mm;" in html
    assert "VSTV6 DIGITAL MEDIA · TELANGANA" in html
    assert "Today's Top Stories" in html
    assert ".lead-story {" in html
    assert ".lead-story .story-intro {" in html
    assert "grid-template-columns: minmax(0, 1fr) 62mm;" in html
    assert ".story-body {" in html
    assert ".lead-story .story-body {" in html
    assert ".newspaper-grid {" in html
    assert ".story-card {" in html
    assert "class=\"story-label\"" in html
    assert "జాతీయం" in html
    assert ".newspaper-content-flow {\n    column-count: 2;" in html
    assert "column-fill: balance;" in html
    assert "column-rule: .3pt solid #cbd5e1;" in html
    assert "max-height: 40mm;" in html
    assert "max-height: 36mm;" in html
    assert "object-fit: contain;" in html
    assert "page-break-inside: avoid" in html
    assert ".edition-bar {\n    display: flex;" in html
    assert "VSTV6 Digital Media · Telangana" in html
    assert 'id="edition-date" datetime="2026-' in html
    assert "margin: 0;" in html
    assert ".newspaper-footer {\n        display: block !important;" in html
    assert "VSTV6 DIGITAL MEDIA · TELANGANA" in html
    assert "font-size: 24pt;" in html
    assert "font-size: 13pt;" in html
    assert "font-size: 9pt;" in html
    assert "page-break-inside: avoid;" in html
    assert "NotoSerifTelugu-Regular.ttf" in html
    assert "NotoSerifTelugu-Bold.ttf" in html
    assert 'font-family: "VSTV6 Noto Serif Telugu", "Nirmala UI", serif;' in html
    assert "VSTV6 Digital Media · Telangana" in html
    assert "ప్రధాన వార్త | TOP STORY" in html
    assert 'action="/admin/newspaper/download-pdf"' not in html
    assert "Download PDF" not in html
    assert "Download HTML" not in html
    assert "function downloadPreviewHtml()" not in html
    assert "Save &amp; Print" in html
    assert 'onclick="window.print()"' in html

def test_newspaper_download_returns_pdf_attachment(app, monkeypatch):
    from io import BytesIO
    import routes.newspaper as newspaper

    monkeypatch.setattr(newspaper, "_require_admin", lambda: None)
    monkeypatch.setattr(
        newspaper,
        "_get_selected_articles",
        lambda ids: [SimpleNamespace(id=42)],
    )
    monkeypatch.setattr(
        newspaper,
        "create_newspaper_pdf",
        lambda articles, edition_date=None: BytesIO(b"%PDF-test"),
    )

    with app.test_request_context(
        "/admin/newspaper/download-pdf",
        method="POST",
        data={"article_ids": ["42"]},
    ):
        response = newspaper.download_pdf.__wrapped__()

    assert response.status_code == 200
    assert response.mimetype == "application/pdf"
    assert "attachment" in response.headers["Content-Disposition"]

def test_collect_rss_cli_uses_saving_mode(monkeypatch, tmp_path):
    from app import create_app
    import services.news_collector as news_collector

    monkeypatch.setenv("SECRET_KEY", "test-secret-only")
    monkeypatch.setenv(
        "DATABASE_URL",
        "sqlite:///" + str(tmp_path / "cli-test.db"),
    )

    dry_run_values = []
    monkeypatch.setattr(
        news_collector,
        "collect_all_feeds",
        lambda dry_run=False: dry_run_values.append(dry_run) or 2,
    )

    app = create_app()
    result = app.test_cli_runner().invoke(
        app.cli,
        ["collect-rss"],
    )

    assert result.exit_code == 0
    assert "New draft articles: 2" in result.output
    assert dry_run_values == [False]

def test_rss_image_extractor_finds_images_embedded_in_feed_content():
    from services.news_collector import get_image_url

    entry = {
        "link": "https://news.example/story",
        "content": [{
            "value": (
                '<p><img src="placeholder.gif" '
                'data-src="/images/story.jpg"></p>'
            ),
        }],
    }

    assert get_image_url(entry) == "https://news.example/images/story.jpg"

def test_article_page_extractor_reads_featured_image_metadata(
    monkeypatch,
):
    import services.article_extractor as extractor

    html = (
        '<meta property="og:image" content="/images/featured.jpg">'
        "<article>Story content</article>"
    ).encode()

    class FakeResponse:
        headers = {"Content-Type": "text/html"}
        encoding = "utf-8"
        url = "https://news.example/redirected/story"

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def iter_content(self, chunk_size):
            return [html]

        def raise_for_status(self):
            return None

    monkeypatch.setattr(
        extractor.requests,
        "get",
        lambda *args, **kwargs: FakeResponse(),
    )
    monkeypatch.setattr(
        extractor.trafilatura,
        "extract",
        lambda *args, **kwargs: "తెలుగు వార్త " * 30,
    )

    text, image_url = extractor.extract_article_page(
        "https://news.example/story"
    )

    assert text == ("తెలుగు వార్త " * 30).strip()
    assert image_url == "https://news.example/images/featured.jpg"

def test_rss_collection_saves_and_backfills_article_page_image(
    app,
    monkeypatch,
):
    from extensions import db
    from models import Article, Category, User
    import services.news_collector as collector

    article_url = "https://news.example/story"
    image_url = "https://images.example/story.jpg"
    entry = {
        "title": "తెలంగాణ తాజా వార్త",
        "summary": "తెలుగు వార్తా సారాంశం",
        "link": article_url,
    }

    with app.app_context():
        author = User(
            email="rss-editor@example.com",
            display_name="తెలుగు సంపాదకుడు",
            password_hash="test-hash",
            role="editor",
        )
        category = Category(
            name_en="National",
            name_te="జాతీయం",
            slug="national",
        )
        db.session.add_all([author, category])
        db.session.commit()

        monkeypatch.setattr(
            collector.feedparser,
            "parse",
            lambda *args, **kwargs: SimpleNamespace(
                entries=[entry],
                bozo=False,
                get=lambda key, default=None: default,
            ),
        )
        monkeypatch.setattr(
            collector,
            "extract_article_page",
            lambda url: ("తెలుగు పూర్తి వార్త " * 20, image_url),
        )

        assert collector.collect_feed("https://feeds.example/rss") == 1
        article = Article.query.filter_by(source_url=article_url).one()
        assert article.image_url == image_url

        article.image_url = None
        db.session.commit()

        assert collector.collect_feed("https://feeds.example/rss") == 0
        assert article.image_url == image_url
