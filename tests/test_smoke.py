import os
import io
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


def test_telugu_article_form_saves_draft_with_uploaded_image(app, tmp_path):
    from extensions import db
    from models import Article, Category, User

    app.config["UPLOAD_FOLDER"] = str(tmp_path / "uploads")
    with app.app_context():
        author = User(
            email="editor@example.com",
            display_name="Editor",
            password_hash="test-hash",
        )
        category = Category(
            name_en="National",
            name_te="జాతీయం",
            slug="national",
        )
        db.session.add_all([author, category])
        db.session.commit()
        author_id = author.id
        category_id = category.id

    client = app.test_client()
    with client.session_transaction() as session:
        session["_user_id"] = str(author_id)
        session["_fresh"] = True

    form_page = client.get("/admin/articles/new")
    assert form_page.status_code == 200
    assert b'name="title_en"' not in form_page.data
    assert b'name="summary_en"' not in form_page.data
    assert b'name="body_en"' not in form_page.data
    assert b'name="image_file"' in form_page.data

    response = client.post(
        "/admin/articles/new",
        data={
            "title_te": "తెలుగు వార్త శీర్షిక",
            "summary_te": "తెలుగు వార్తా సారాంశం",
            "body_te": "తెలుగు పూర్తి వార్త.",
            "category_id": str(category_id),
            "image_file": (
                io.BytesIO(
                    b"\x89PNG\r\n\x1a\n"
                    b"\x00\x00\x00\rIHDR"
                    b"\x00\x00\x00\x01\x00\x00\x00\x01"
                    b"\x08\x06\x00\x00\x00"
                ),
                "featured.png",
            ),
        },
        content_type="multipart/form-data",
    )

    assert response.status_code == 302
    with app.app_context():
        article = Article.query.one()
        assert article.status == "draft"
        assert article.language == "te"
        assert article.title_en is None
        assert article.summary_en is None
        assert article.body_en is None
        assert article.title_te == "తెలుగు వార్త శీర్షిక"
        assert article.image_url.startswith("/uploads/")
        uploaded_file = tmp_path / "uploads" / article.image_url.split("/")[-1]
        assert uploaded_file.is_file()
    assert client.get(article.image_url).status_code == 200


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
