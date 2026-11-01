
from datetime import timezone
from email.utils import format_datetime

from flask import (
    Blueprint,
    Response,
    current_app,
    render_template,
    url_for,
)

from models import Article

seo_bp = Blueprint("seo", __name__)


def absolute_url(path):
    """Build an absolute URL using the configured production domain."""
    site_url = current_app.config["SITE_URL"].rstrip("/")
    return f"{site_url}/{path.lstrip('/')}"


def _eligible_telugu_articles():
    """
    Yield published Telugu articles with valid titles and slugs.

    Articles without a Telugu story are excluded because the article
    detail route may return 404 for them.
    """
    articles = (
        Article.query
        .filter(
            Article.status == "published",
            Article.language == "te",
            Article.title_te.isnot(None),
            Article.title_te != "",
            Article.slug.isnot(None),
            Article.slug != "",
        )
        .order_by(Article.published_at.desc())
        .yield_per(100)
    )

    for article in articles:
        if article.has_telugu_story:
            yield article


def _lastmod(article):
    """Return an ISO-formatted date for a sitemap entry."""
    value = getattr(article, "updated_at", None)

    if value is None:
        value = getattr(article, "published_at", None)

    if value is None:
        return None

    return value.date().isoformat()


def _add_page(pages, seen_urls, path, lastmod=None):
    """Add a unique absolute URL to the sitemap."""
    if not path:
        return

    absolute = absolute_url(path)

    if absolute in seen_urls:
        return

    seen_urls.add(absolute)

    pages.append({
        "loc": absolute,
        "lastmod": lastmod,
    })


@seo_bp.get("/robots.txt")
def robots():
    """Provide crawler instructions and the sitemap location."""
    sitemap_url = absolute_url("/sitemap.xml")

    content = (
        "User-agent: *\n"
        "Allow: /\n"
        "Disallow: /admin/\n"
        "Disallow: /auth/\n"
        f"Sitemap: {sitemap_url}\n"
    )

    return Response(
        content,
        status=200,
        mimetype="text/plain",
    )


@seo_bp.get("/sitemap.xml")
def sitemap():
    """Generate a sitemap containing public pages and eligible articles."""
    pages = []
    seen_urls = set()

    # Homepage.
    _add_page(
        pages,
        seen_urls,
        url_for("public.home"),
    )

    # Static public pages. Add only routes that exist in your application.
    public_endpoints = (
        "public.about",
        "public.contact",
    )

    for endpoint in public_endpoints:
        try:
            path = url_for(endpoint)
        except Exception:
            # The endpoint may not exist in this application.
            continue

        _add_page(pages, seen_urls, path)

    # Published Telugu articles.
    for article in _eligible_telugu_articles():
        try:
            article_path = url_for(
                "articles.detail",
                slug=article.slug,
            )
        except Exception:
            current_app.logger.exception(
                "Could not build URL for article ID %s",
                article.id,
            )
            continue

        _add_page(
            pages,
            seen_urls,
            article_path,
            _lastmod(article),
        )

    response = Response(
        render_template("sitemap.xml", pages=pages),
        status=200,
        mimetype="application/xml",
    )

    response.headers["Cache-Control"] = "public, max-age=300"

    return response


@seo_bp.get("/feed.xml")
def feed():
    """Generate an RSS feed containing the latest 50 eligible articles."""
    items = []

    for article in _eligible_telugu_articles():
        dt = article.published_at

        if dt and dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        article_url = absolute_url(
            url_for(
                "articles.detail",
                slug=article.slug,
            )
        )

        items.append({
            "title": article.telugu_title or article.title_te or "",
            "link": article_url,
            "guid": article_url,
            "description": article.telugu_summary or "",
            "pubDate": format_datetime(dt) if dt else "",
        })

        if len(items) >= 50:
            break

    return Response(
        render_template(
            "feed.xml",
            items=items,
            site_name=current_app.config["SITE_NAME"],
            site_url=current_app.config["SITE_URL"].rstrip("/"),
        ),
        status=200,
        mimetype="application/rss+xml; charset=utf-8",
    )
