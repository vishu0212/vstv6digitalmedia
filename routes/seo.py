
from datetime import timezone
from email.utils import format_datetime

from flask import (
    Blueprint,
    Response,
    current_app,
    render_template,
    url_for,
)

from sqlalchemy import func

from models import Article

seo_bp = Blueprint("seo", __name__)


def absolute_url(path):
    """Build an absolute URL using the configured production domain."""
    site_url = current_app.config["SITE_URL"].rstrip("/")
    return f"{site_url}/{path.lstrip('/')}"


def _eligible_articles():
    """
    Return all published English and Telugu articles
    that have valid public content and slugs.
    """
    articles = (
        Article.query
        .filter(
            func.lower(Article.status) == "published",
            Article.slug.isnot(None),
            Article.slug != "",
            Article.published_at.isnot(None),
            Article.title_en.isnot(None),
            Article.title_en != "",
            Article.body_en.isnot(None),
            Article.body_en != "",
        )
        .order_by(Article.published_at.desc())
        .yield_per(100)
    )

    for article in articles:
        # English articles require English content.
        # Telugu articles require a complete Telugu story.
        if article.language == "te":
            if article.has_telugu_story:
                yield article
        elif article.language in ("en", "both"):
            yield article


def _lastmod(article):
    """Return the latest available modification date."""
    value = (
        getattr(article, "updated_at", None)
        or getattr(article, "published_at", None)
    )

    if value is None:
        return None

    return value.date().isoformat()


def _add_page(pages, seen_urls, path, lastmod=None):
    """Add a unique absolute URL."""
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
    """Provide crawler instructions."""
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
    """Generate a dynamic sitemap from public database records."""

    pages = []
    seen_urls = set()

    # Homepage
    _add_page(
        pages,
        seen_urls,
        url_for("public.home"),
    )

    # Static public pages
    public_endpoints = (
        "public.about",
        "public.contact",
    )

    for endpoint in public_endpoints:
        try:
            path = url_for(endpoint)
            _add_page(pages, seen_urls, path)
        except Exception:
            current_app.logger.warning(
                "Sitemap endpoint unavailable: %s",
                endpoint,
            )

    # All eligible published articles
    for article in _eligible_articles():

        try:
            article_path = url_for(
                "articles.detail",
                slug=article.slug,
            )

            _add_page(
                pages,
                seen_urls,
                article_path,
                _lastmod(article),
            )

        except Exception:
            current_app.logger.exception(
                "Sitemap URL generation failed for article ID %s",
                article.id,
            )

    # Render XML
    response = Response(
        render_template(
            "sitemap.xml",
            pages=pages,
        ),
        status=200,
        mimetype="application/xml",
    )

    response.headers["Cache-Control"] = "public, max-age=300"
    return response


@seo_bp.get("/feed.xml")
def feed():
    """Generate RSS feed with the latest 50 eligible articles."""

    items = []

    for article in _eligible_articles():

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
            "title": article.display_title or "",
            "link": article_url,
            "guid": article_url,
            "description": article.display_summary or "",
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
        mimetype="application/rss+xml",
    )
