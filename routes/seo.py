from datetime import timezone
from email.utils import format_datetime
from flask import Blueprint, Response, current_app, render_template, url_for
from models import Article
seo_bp = Blueprint("seo", __name__)

@seo_bp.get("/robots.txt")
def robots():
    return Response(f"User-agent: *\nAllow: /\nDisallow: /admin/\nDisallow: /auth/\nSitemap: {current_app.config['SITE_URL']}/sitemap.xml\n", mimetype="text/plain")

@seo_bp.get("/sitemap.xml")
def sitemap():
    pages = [{"loc": current_app.config["SITE_URL"] + url_for("public.home"), "lastmod": None}]
    for article in Article.query.filter_by(status="published").order_by(Article.published_at.desc()).all():
        pages.append({"loc": current_app.config["SITE_URL"] + url_for("articles.detail", slug=article.slug),
                      "lastmod": (article.updated_at or article.published_at).date().isoformat()})
    return render_template("sitemap.xml", pages=pages), 200, {"Content-Type": "application/xml; charset=utf-8"}

@seo_bp.get("/feed.xml")
def feed():
    items = []
    for article in Article.query.filter_by(status="published").order_by(Article.published_at.desc()).limit(50).all():
        dt = article.published_at
        if dt and dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        items.append({"title": article.title_en, "link": current_app.config["SITE_URL"] + url_for("articles.detail", slug=article.slug),
                      "guid": current_app.config["SITE_URL"] + url_for("articles.detail", slug=article.slug),
                      "description": article.summary_en, "pubDate": format_datetime(dt) if dt else ""})
    return render_template("feed.xml", items=items, site_name=current_app.config["SITE_NAME"], site_url=current_app.config["SITE_URL"]), 200, {"Content-Type": "application/rss+xml; charset=utf-8"}
