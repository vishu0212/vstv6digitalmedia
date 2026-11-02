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
                slug="telugu-story",
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
    assert client.get("/news/telugu-story").status_code == 200
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
    from services.newspaper_pdf import get_styles

    styles = get_styles()

    assert styles["NewsBody"].alignment == TA_JUSTIFY
    assert styles["NewsHeadline"].alignment == TA_LEFT

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
