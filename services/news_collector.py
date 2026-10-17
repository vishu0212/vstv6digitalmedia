
from __future__ import annotations

import hashlib
import logging
import re
from html import unescape
from urllib.parse import urlparse
from urllib.request import Request, urlopen

import feedparser

from extensions import db
from models import Article, Category, User

logger = logging.getLogger(__name__)

# Existing English feeds plus Telugu feeds.
DEFAULT_FEEDS = [
    "https://www.thehindu.com/news/national/telangana/feeder/default.rss",
    "https://n24india.com/rss/category/telangana.xml",
    "https://n24india.com/rss/category/hyderabad.xml",
    "https://feeds.bbci.co.uk/news/world/rss.xml",
    "https://feeds.bbci.co.uk/news/technology/rss.xml",

    # Official Oneindia Telugu RSS feeds
    "https://telugu.oneindia.com/rss/feeds/oneindia-telugu-fb.xml",
    "https://telugu.oneindia.com/rss/feeds/telugu-news-fb.xml",
    "https://telugu.oneindia.com/rss/feeds/telugu-sports-fb.xml",
    "https://telugu.oneindia.com/rss/feeds/telugu-entertainment-fb.xml",
    "https://telugu.oneindia.com/rss/feeds/telugu-science-technology-fb.xml",
    "https://telugu.oneindia.com/rss/feeds/education-jobs-fb.xml",
    "https://telugu.oneindia.com/rss/feeds/artificial-intelligence-fb.xml",
]

REQUEST_TIMEOUT = 15
MAX_RESPONSE_BYTES = 5 * 1024 * 1024
MAX_PER_FEED = 25
USER_AGENT = "VSTV6NewsCollector/1.0"

TELUGU_SCRIPT = re.compile(r"[\u0C00-\u0C7F]")


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
    """Read RSS_FEEDS from Flask configuration or use defaults."""
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

    # If RSS_FEEDS is configured, use it. Otherwise use defaults.
    return list(dict.fromkeys(feeds or DEFAULT_FEEDS))


def is_telugu_entry(feed_url: str, title: str) -> bool:
    """
    Identify Telugu items using the publisher host or Telugu script.

    Note: a Telugu headline from an English-language feed will also
    be classified as Telugu.
    """
    host = urlparse(feed_url).netloc.lower()

    telugu_publisher = (
        host == "telugu.oneindia.com"
        or host.endswith(".telugu.oneindia.com")
    )

    return telugu_publisher or bool(TELUGU_SCRIPT.search(title))


def get_author() -> User | None:
    """Choose an existing active admin/editor as the author."""
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
                "telangana", "hyderabad", "warangal",
                "karimnagar", "mancherial", "khammam",
                "nizamabad", "nalgonda", "adilabad",
                "sircilla", "siddipet", "mahbubnagar",
                "తెలంగాణ", "హైదరాబాద్", "వరంగల్",
                "కరీంనగర్", "ఖమ్మం", "నిజామాబాద్",
            ),
            "telangana",
        ),
        (
            (
                "technology", "artificial intelligence",
                "software", "cyber", "టెక్నాలజీ",
                "సాంకేతిక", "ఏఐ",
            ),
            "technology",
        ),
        (
            (
                "business", "economy", "markets",
                "finance", "stock market", "వ్యాపారం",
                "ఆర్థిక",
            ),
            "business",
        ),
        (
            ("cricket", "football", "sports", "tournament", "క్రికెట్", "క్రీడలు"),
            "sports",
        ),
        (
            ("cinema", "entertainment", "movies", "film", "సినిమా", "వినోదం"),
            "entertainment",
        ),
        (
            ("international", "world news", "global", "అంతర్జాతీయ"),
            "world",
        ),
    ]

    for keywords, slug in rules:
        if any(keyword in text for keyword in keywords):
            category = Category.query.filter_by(slug=slug).first()
            if category:
                return category

    # Prefer a known general category if no rule matches.
    for slug in ("national", "telangana"):
        category = Category.query.filter_by(slug=slug).first()
        if category:
            return category

    # category_id is required by the Article model.
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
            image_url = valid_http_url(
                item.get("href") or item.get("url")
            )
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
    """Fetch an RSS feed with a timeout and response-size limit."""
    request = Request(
        feed_url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept": (
                "application/rss+xml, application/atom+xml, "
                "application/xml, text/xml"
            ),
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
    Import RSS headlines as drafts.

    This does not publish articles automatically or copy full publisher
    article text. Editors/admins must verify facts and reuse permissions.

    Telugu RSS entries populate Telugu fields. Because the current Article
    model requires English fields too, the original title and summary are
    also placed in those required fields. This is not a translation.
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
                feed_title = clean_html(feed.feed.get("title", ""))
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

                        # Avoid importing the same original URL twice.
                        existing = Article.query.filter_by(
                            source_url=source_url
                        ).first()

                        if existing:
                            results["duplicates"] += 1
                            continue

                        summary = clean_html(entry.get("summary", ""))
                        summary = summary[:490]

                        if not summary:
                            summary = (
                                "Imported headline. Open the original "
                                "publisher link to review the report."
                            )

                        category = get_category(entry, feed_title)

                        if not category:
                            logger.warning(
                                "No category available; skipping %s",
                                source_url,
                            )
                            results["skipped"] += 1
                            continue

                        image_url = get_image_url(entry)
                        telugu = is_telugu_entry(feed_url, title)

                        if telugu:
                            # The English fields are required by the
                            # current database model. Do not treat these
                            # values as an English translation.
                            article = Article(
                                title_en=title[:220],
                                title_te=title[:220],
                                slug=make_slug(title, source_url),
                                summary_en=summary[:500],
                                summary_te=summary[:500],
                                body_en=(
                                    f"Source: {feed_title or 'RSS feed'}\n\n"
                                    "Telugu RSS draft. Verify the facts and "
                                    "prepare an original report before "
                                    "publishing.\n\n"
                                    f"Original report: {source_url}"
                                ),
                                body_te=(
                                    "ఇది RSS ద్వారా దిగుమతి చేసిన తెలుగు "
                                    "వార్తా డ్రాఫ్ట్. వాస్తవాలను ధృవీకరించి, "
                                    "స్వంత కథనాన్ని సిద్ధం చేసి ఆమోదం "
                                    "తర్వాత మాత్రమే ప్రచురించండి.\n\n"
                                    f"మూల వార్త: {source_url}"
                                ),
                                language="te",
                                category_id=category.id,
                                author_id=author.id,
                                source_name=(feed_title or "RSS feed")[:200],
                                source_url=source_url,
                                image_url=image_url,
                                status="draft",
                            )
                        else:
                            article = Article(
                                title_en=title[:220],
                                slug=make_slug(title, source_url),
                                summary_en=summary[:500],
                                body_en=(
                                    f"Source: {feed_title or 'RSS feed'}\n\n"
                                    "Automatically imported news draft. "
                                    "Verify the facts and prepare an "
                                    "original report before publishing.\n\n"
                                    f"Original report: {source_url}"
                                ),
                                language="en",
                                category_id=category.id,
                                author_id=author.id,
                                source_name=(feed_title or "RSS feed")[:200],
                                source_url=source_url,
                                image_url=image_url,
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
