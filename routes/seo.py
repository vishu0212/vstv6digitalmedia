
from datetime import timezone
from email.utils import format_datetime

from flask import Blueprint, Response, current_app, render_template, url_for
from models import Article

seo_bp = Blueprint("seo", __name__)


def absolute_url(path):
    """Build an absolute URL using the configured production domain."""
    site_url = current_app.config["SITE_URL"].rstrip("/")
    return f"{site_url}/{path.lstrip('/')}"


@seo_bp.get("/robots.txt")
def robots():
    sitemap_url = absolute_url("/sitemap.xml")

    content = (
        "User-agent: *\n"
        "Allow: /\n"
        "Disallow: /admin/\n"
        "Disallow: /auth/\n"
        f"Sitemap: {sitemap_url}\n"
    )

    return Response(content, mimetype="text/plain")


@seo_bp.get("/sitemap.xml")
def sitemap():
    pages = [
        {
            "loc": absolute_url(url_for("public.home")),
            "lastmod": None,
        }
    ]

    articles = (
        Article.query
        .filter_by(status="published")
        .order_by(Article.published_at.desc())
        .all()
    )

    for article in articles:
        article_path = url_for(
            "articles.detail",
            slug=article.slug
        )

        last_modified = article.updated_at or article.published_at

        pages.append({
            "loc": absolute_url(article_path),
            "lastmod": (
                last_modified.date().isoformat()
                if last_modified
                else None
            ),
        })

    response = Response(
        render_template("sitemap.xml", pages=pages),
        status=200,
        mimetype="application/xml",
    )
    return response


@seo_bp.get("/feed.xml")
def feed():
    items = []

    articles = (
        Article.query
        .filter_by(status="published")
        .order_by(Article.published_at.desc())
        .limit(50)
        .all()
    )

    for article in articles:
        dt = article.published_at

        if dt and dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        article_url = absolute_url(
            url_for("articles.detail", slug=article.slug)
        )

        items.append({
            "title": article.title_en,
            "link": article_url,
            "guid": article_url,
            "description": article.summary_en or "",
            "pubDate": format_datetime(dt) if dt else "",
        })

    return (
        render_template(
            "feed.xml",
            items=items,
            site_name=current_app.config["SITE_NAME"],
            site_url=current_app.config["SITE_URL"].rstrip("/"),
        ),
        200,
        {"Content-Type": "application/rss+xml; charset=utf-8"},
    )
