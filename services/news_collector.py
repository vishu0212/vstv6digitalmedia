
from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime, timezone
from html import unescape
from urllib.parse import urlparse
from urllib.request import Request, urlopen

import feedparser

from extensions import db
from models import Article, Category, User

logger = logging.getLogger(__name__)

DEFAULT_FEEDS = [
    "https://www.thehindu.com/news/national/telangana/feeder/default.rss",
    "https://n24india.com/rss/category/telangana.xml",
    "https://n24india.com/rss/category/hyderabad.xml",
    "https://feeds.bbci.co.uk/news/world/rss.xml",
    "https://feeds.bbci.co.uk/news/technology/rss.xml",
]

REQUEST_TIMEOUT = 15
MAX_RESPONSE_BYTES = 5 * 1024 * 1024
MAX_PER_FEED = 25
USER_AGENT = "VSTV6NewsCollector/1.0"


def clean_html(value: str | None) -> str:
    """Convert HTML fragments into readable plain text."""
    if not value:
        return ""

    value = unescape(str(value))
    value = re.sub(r"(?is)<(script|style).*?>.*?</\1>", " ", value)
    value = re.sub(r"(?s)<[^>]+>", " ", value)
    value = re.sub(r"\s+", " ", value)

    return value.strip()


def valid_http_url(value: str | None) -> str | None:
    """Accept only absolute HTTP/HTTPS URLs."""
    if not value:
        return None

    value = str(value).strip()
    parsed = urlparse(value)

    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None

    return value


def configured_feeds() -> list[str]:
    """Read RSS_FEEDS from Flask configuration, or use defaults."""
    from flask import current_app, has_app_context

    if has_app_context():
        configured = current_app.config.get("RSS_FEEDS", [])
    else:
        configured = []

    if isinstance(configured, str):
        configured = configured.split(",")

    feeds = [
        valid_http_url(item.strip())
        for item in (configured or [])
        if item and item.strip()
    ]

    feeds = [feed for feed in feeds if feed]

    return list(dict.fromkeys(feeds or DEFAULT_FEEDS))


def get_author() -> User | None:
    """Choose an existing active admin/editor as the article author."""
    query = User.query.filter_by(active=True)

    author = query.filter_by(role="admin").first()

    if author:
        return author

    return query.filter_by(role="editor").first()


def get_category(entry, feed_title: str | None = None) -> Category | None:
    """Match a story to one of the existing VSTV6 categories."""
    tags = entry.get("tags", []) or []

    tag_text = " ".join(
        str(tag.get("term", ""))
        for tag in tags
        if isinstance(tag, dict)
    )

    text = " ".join(
        [
            str(entry.get("title", "")),
            str(entry.get("summary", "")),
            str(feed_title or ""),
            tag_text,
        ]
    ).lower()

    rules = [
        (
            (
                "telangana",
                "hyderabad",
                "warangal",
                "karimnagar",
                "mancherial",
                "khammam",
                "nizamabad",
                "nalgonda",
                "adilabad",
                "sircilla",
                "siddipet",
                "mahbubnagar",
            ),
            "telangana",
        ),
        (
            ("technology", "artificial intelligence", "software", "cyber"),
            "technology",
        ),
        (
            ("business", "economy", "markets", "finance", "stock market"),
            "business",
        ),
        (
            ("cricket", "football", "sports", "tournament"),
            "sports",
        ),
        (
            ("cinema", "entertainment", "movies", "film"),
            "entertainment",
        ),
        (
            ("international", "world news", "global"),
            "world",
        ),
    ]

    for keywords, slug in rules:
        if any(keyword in text for keyword in keywords):
            category = Category.query.filter_by(slug=slug).first()
            if category:
                return category

    category = Category.query.filter_by(slug="national").first()

    if category:
        return category

    return Category.query.order_by(Category.id.asc()).first()


def get_image_url(entry) -> str | None:
    """Extract an image URL when the RSS entry provides one."""
    for item in entry.get("media_content", []) or []:
        if isinstance(item, dict):
            image_url = valid_http_url(item.get("url"))
            if image_url:
                return image_url

    for item in entry.get("media_thumbnail", []) or []:
        if isinstance(item, dict):
            image_url = valid_http_url(item.get("url"))
            if image_url:
                return image_url

    for item in entry.get("links", []) or []:
        if isinstance(item, dict) and item.get("type", "").startswith("image/"):
            image_url = valid_http_url(item.get("href"))
            if image_url:
                return image_url

    for item in entry.get("enclosures", []) or []:
        if isinstance(item, dict):
            image_url = valid_http_url(item.get("href") or item.get("url"))
            media_type = str(item.get("type", "")).lower()

            if image_url and media_type.startswith("image/"):
                return image_url

    return None


def make_slug(title: str, source_url: str) -> str:
    """Generate a readable, unique slug."""
    base = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    base = base[:180].strip("-") or "news"

    digest = hashlib.sha1(
        source_url.encode("utf-8")
    ).hexdigest()[:10]

    slug = f"{base}-{digest}"
    candidate = slug
    counter = 2

    while Article.query.filter_by(slug=candidate).first():
        candidate = f"{slug}-{counter}"
        counter += 1

    return candidate[:240]


def fetch_feed(feed_url: str):
    """Fetch a feed with a timeout and a response-size limit."""
    request = Request(
        feed_url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": "application/rss+xml, application/atom+xml, application/xml, text/xml",
        },
    )

    with urlopen(request, timeout=REQUEST_TIMEOUT) as response:
        status = getattr(response, "status", 200)

        if status != 200:
            raise RuntimeError(f"Feed returned HTTP {status}")

        data = response.read(MAX_RESPONSE_BYTES + 1)

    if len(data) > MAX_RESPONSE_BYTES:
        raise ValueError("Feed exceeds the 5 MB size limit")

    parsed = feedparser.parse(data)

    if parsed.bozo and not parsed.entries:
        raise ValueError("Feed could not be parsed")

    return parsed


def entry_source_url(entry) -> str | None:
    """Get the original publisher URL from an RSS entry."""
    link = valid_http_url(entry.get("link"))

    if link:
        return link

    for item in entry.get("links", []) or []:
        if isinstance(item, dict):
            link = valid_http_url(item.get("href"))
            if link:
                return link

    return None


def import_rss_drafts(app=None, max_per_feed: int = MAX_PER_FEED) -> dict:
    """
    Import RSS headlines into Article as drafts.

    This does not publish articles automatically or copy full publisher
    article text. Editors/admins should verify facts and licensing before
    editing and publishing.
    """
    from flask import current_app

    if app is None:
        app = current_app._get_current_object()

    results = {
        "feeds_checked": 0,
        "created": 0,
        "duplicates": 0,
        "skipped": 0,
        "errors": 0,
    }

    with app.app_context():
        feeds = configured_feeds()
        author = get_author()

        if not author:
            logger.error(
                "RSS import stopped: no active admin/editor user exists."
            )
            results["errors"] += 1
            return results

        for feed_url in feeds:
            results["feeds_checked"] += 1

            try:
                feed = fetch_feed(feed_url)
                feed_title = clean_html(
                    feed.feed.get("title", "")
                )

                entries = feed.entries[:max_per_feed]

                for entry in entries:
                    try:
                        title = clean_html(entry.get("title", ""))

                        if not title:
                            results["skipped"] += 1
                            continue

                        source_url = entry_source_url(entry)

                        if not source_url:
                            results["skipped"] += 1
                            continue

                        # Check both source URL and generated slug.
                        existing = Article.query.filter_by(
                            source_url=source_url
                        ).first()

                        if existing:
                            results["duplicates"] += 1
                            continue

                        summary = clean_html(
                            entry.get("summary", "")
                        )

                        # Do not copy the full article from the publisher.
                        summary = summary[:490]

                        if not summary:
                            summary = (
                                "Imported headline. Open the original "
                                "publisher link to review the full report."
                            )

                        category = get_category(entry, feed_title)

                        article = Article(
                            title_en=title[:220],
                            slug=make_slug(title, source_url),
                            summary_en=summary,
                            body_en=(
                                f"Source: {feed_title or 'RSS feed'}\n\n"
                                "This is an automatically imported news "
                                "draft. Verify the facts and prepare an "
                                "original report before publishing.\n\n"
                                f"Original report: {source_url}"
                            ),
                            language="en",
                            category_id=category.id if category else None,
                            author_id=author.id,
                            source_name=(feed_title or "RSS feed")[:150],
                            source_url=source_url,
                            image_url=get_image_url(entry),
                            status="draft",
                        )

                        db.session.add(article)
                        db.session.commit()
                        results["created"] += 1

                    except Exception:
                        db.session.rollback()
                        results["errors"] += 1
                        logger.exception(
                            "Could not import an RSS entry from %s",
                            feed_url,
                        )

            except Exception:
                db.session.rollback()
                results["errors"] += 1
                logger.exception(
                    "Could not read RSS feed: %s",
                    feed_url,
                )

        logger.info("RSS import results: %s", results)

    return results


def collect_feeds(app=None) -> int:
    """Compatibility wrapper for the existing Flask CLI command."""
    results = import_rss_drafts(app=app)

    print(
        "RSS results: "
        f"{results['created']} new drafts, "
        f"{results['duplicates']} duplicates, "
        f"{results['skipped']} skipped, "
        f"{results['errors']} errors."
    )

    return results["created"]
