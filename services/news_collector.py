"""
RSS News Collector for VSTV6 Digital Media.

Features:
- Loads RSS feeds from .env
- Extracts article text
- Detects Telugu and English
- Classifies news categories
- Skips duplicate articles
- Generates unique slugs
- Saves articles as drafts
- Supports dry-run mode
- Never automatically publishes articles
"""

from __future__ import annotations

import logging
import os
import re
import unicodedata
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urlparse

import feedparser
from dotenv import load_dotenv

from extensions import db
from models import Article, Category, User
from models.article import contains_telugu_script, is_telugu_summary
from services.article_extractor import extract_article_text


logger = logging.getLogger(__name__)

load_dotenv()


# ============================================================
# CONFIGURATION
# ============================================================

RSS_FEEDS = [
    url.strip()
    for url in os.getenv("RSS_FEEDS", "").split(",")
    if url.strip()
]

# Backward compatibility with existing routes.
configured_feeds = RSS_FEEDS

MINIMUM_ARTICLE_LENGTH = 200
MAX_TITLE_LENGTH = 220
MAX_SUMMARY_LENGTH = 500
MAX_SOURCE_URL_LENGTH = 1000

TELUGU_CHAR_RE = re.compile(r"[\u0C00-\u0C7F]")


# ============================================================
# CATEGORY KEYWORDS
# ============================================================

CATEGORY_KEYWORDS = {
    "Sports": (
        "cricket", "t20", "odi", "test match", "ipl",
        "world cup", "wicket", "bowler", "batsman",
        "batter", "innings", "century", "football",
        "tennis", "badminton", "olympics", "athlete",
        "championship", "tournament", "fifa",
        "టీమిండియా", "క్రికెట్", "క్రీడలు", "వికెట్",
        "బౌలర్", "బ్యాటర్", "శతకం", "ప్రపంచకప్",
        "ఐపీఎల్", "పరుగులు", "ఫుట్‌బాల్", "టెన్నిస్",
        "ఒలింపిక్స్", "పతకం", "టోర్నమెంట్",
    ),

    "Entertainment": (
        "movie review", "film review", "box office",
        "actor", "actress", "cinema", "movie", "trailer",
        "teaser", "bollywood", "tollywood", "kollywood",
        "ott release", "web series", "celebrity",
        "upcoming movie", "movie release", "singer",
        "మూవీ రివ్యూ", "సినిమా", "నటి", "నటుడు",
        "ట్రైలర్", "బాలీవుడ్", "టాలీవుడ్", "వినోదం",
        "సినీ", "త్రిష", "కోలీవుడ్", "హీరోయిన్",
        "హీరో", "ఓటీటీ", "దర్శకుడు", "దర్శకురాలు",
        "సినిమా విడుదల", "వెబ్ సిరీస్",
    ),

    "Technology": (
        "iphone", "smartphone", "cybersecurity",
        "data breach", "data leak", "artificial intelligence",
        "ai model", "software update", "technology",
        "tech news", "video game", "gaming", "app update",
        "cyber attack", "laptop", "smartwatch", "android update",
        "electric vehicle", "gadget", "google", "microsoft",
        "openai", "chatgpt", "robotics", "satellite launch",
        "సాంకేతికత", "ఐఫోన్", "డేటా లీక్", "సైబర్",
        "టెక్నాలజీ", "ఏఐ", "కృత్రిమ మేధస్సు",
        "స్మార్ట్‌ఫోన్", "మొబైల్", "సాఫ్ట్‌వేర్",
        "సైబర్ దాడి", "టెక్ వార్తలు", "ఎలక్ట్రిక్ వాహనం",
        "సాఫ్ట్‌వేర్ అప్‌డేట్", "వీడియో గేమ్",
    ),

    "Business": (
        "global markets", "stock market", "share market",
        "shares", "sensex", "nifty", "stock prices",
        "quarterly results", "company earnings", "inflation",
        "gdp growth", "rupee falls", "ipo", "investment",
        "revenue", "profit", "banking", "interest rate",
        "mutual fund", "share price", "business news",
        "economic growth", "financial results", "gold price",
        "silver price", "startup funding", "market crash",
        "స్టాక్ మార్కెట్", "షేర్ మార్కెట్", "వ్యాపారం",
        "పెట్టుబడి", "లాభాలు", "బ్యాంకింగ్", "ఐపీఓ",
        "బంగారం ధర", "వెండి ధర", "ఆర్థిక వృద్ధి",
        "కంపెనీ లాభాలు", "షేర్ల ధర", "వ్యాపార వార్తలు",
        "రియల్ ఎస్టేట్", "ఆర్థిక మార్కెట్",
    ),

    "World": (
        "united states", "usa", "america", "united kingdom",
        "rwanda", "venezuela", "donald trump", "white house",
        "international", "foreign ministry", "overseas",
        "european union", "israel", "iran", "ukraine",
        "russia", "china government", "world news",
        "united nations", "foreign policy", "north korea",
        "south korea", "global summit", "middle east",
        "అమెరికా", "అంతర్జాతీయ", "విదేశీ", "ప్రపంచం",
        "వెనిజులా", "ప్రతిపక్ష నేత", "విదేశాంగ శాఖ",
        "ప్రపంచ రాజకీయాలు", "ఇజ్రాయెల్", "ఇరాన్",
        "రష్యా", "ఉక్రెయిన్", "ఐక్యరాజ్యసమితి",
    ),

    "Telangana": (
        "telangana", "hyderabad", "revanth reddy", "kcr",
        "ktr", "mancherial", "bellampalli", "warangal",
        "karimnagar", "nizamabad", "khammam", "adilabad",
        "telangana government", "telangana police",
        "telangana assembly", "telangana high court",
        "telangana education", "telangana minister",
        "తెలంగాణ", "హైదరాబాద్", "రేవంత్ రెడ్డి",
        "కేసీఆర్", "కేటీఆర్", "మంచిర్యాల",
        "బెల్లంపల్లి", "వరంగల్", "కరీంనగర్",
        "నిజామాబాద్", "ఖమ్మం", "ఆదిలాబాద్",
        "తెలంగాణ ప్రభుత్వం", "తెలంగాణ పోలీస్",
        "తెలంగాణ హైకోర్టు", "తెలంగాణ వార్తలు",
    ),

    "National": (
        "indian government", "union government", "new delhi",
        "supreme court of india", "lok sabha", "rajya sabha",
        "parliament of india", "prime minister of india",
        "central government", "indian army", "indian navy",
        "indian railways", "indian constitution", "union budget",
        "national news", "india", "భారత్", "ఇండియా",
        "కేంద్ర ప్రభుత్వం", "సుప్రీంకోర్టు", "లోక్‌సభ",
        "రాజ్యసభ", "భారత ప్రభుత్వం", "భారత సైన్యం",
        "భారత రాజ్యాంగం", "కేంద్ర మంత్రివర్గం",
        "జాతీయ వార్తలు", "కేంద్ర మంత్రి", "కేంద్ర బడ్జెట్",
    ),
}


CATEGORY_PRIORITY = (
    "Sports",
    "Entertainment",
    "Technology",
    "Business",
    "World",
    "Telangana",
    "National",
)


INDIAN_STATE_KEYWORDS = (
    "tamil nadu", "tamilnadu", "chennai",
    "andhra pradesh", "amaravati", "visakhapatnam",
    "karnataka", "bengaluru", "bangalore",
    "kerala", "kochi", "maharashtra", "mumbai",
    "pune", "uttar pradesh", "lucknow",
    "madhya pradesh", "bhopal", "rajasthan", "jaipur",
    "gujarat", "ahmedabad", "west bengal", "kolkata",
    "bihar", "patna", "odisha", "bhubaneswar",
    "punjab", "chandigarh", "haryana", "assam",
    "goa", "jharkhand", "manipur", "meghalaya",
    "తమిళనాడు", "చెన్నై", "ఆంధ్రప్రదేశ్", "కర్ణాటక",
    "కేరళ", "మహారాష్ట్ర", "ఉత్తరప్రదేశ్",
    "రాజస్థాన్", "గుజరాత్", "పశ్చిమ బెంగాల్",
    "బీహార్", "ఒడిశా", "పంజాబ్", "హర్యానా",
)


# ============================================================
# GENERAL HELPERS
# ============================================================

def clean_text(value: object) -> str:
    """Normalize whitespace and return a string."""
    if value is None:
        return ""

    return re.sub(r"\s+", " ", str(value)).strip()


def clean_article_body(value: object) -> str:
    """Normalize article whitespace while preserving paragraph breaks."""
    if value is None:
        return ""

    text = str(value).replace("\r\n", "\n").replace("\r", "\n")
    lines = [
        re.sub(r"[ \t]+", " ", line).strip()
        for line in text.split("\n")
    ]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def normalize_for_matching(value: str) -> str:
    """Normalize Unicode and case for keyword matching."""
    return unicodedata.normalize(
        "NFKC",
        clean_text(value),
    ).casefold()


def contains_telugu(text: str) -> bool:
    """Check whether text contains Telugu characters."""
    return bool(TELUGU_CHAR_RE.search(text or ""))


def detect_language(
    title: str,
    summary: str = "",
    body: str = "",
) -> str:
    """Detect Telugu or English using the headline, summary, and body."""
    if (
        contains_telugu(title)
        or contains_telugu(summary)
        or contains_telugu(body)
    ):
        return "te"

    return "en"


def normalize_source_url(url: str) -> str:
    """Validate an HTTP(S) URL and remove its fragment."""
    url = clean_text(url)

    if not url or len(url) > MAX_SOURCE_URL_LENGTH:
        return ""

    try:
        parsed = urlparse(url)

        if parsed.scheme.lower() not in {"http", "https"}:
            return ""

        if not parsed.hostname:
            return ""

        return parsed._replace(fragment="").geturl()

    except (TypeError, ValueError):
        return ""


def parse_published_date(entry) -> datetime | None:
    """Parse the RSS publication date as an aware UTC datetime."""
    value = entry.get("published") or entry.get("updated")

    if value:
        try:
            result = parsedate_to_datetime(value)

            if result.tzinfo is None:
                result = result.replace(tzinfo=timezone.utc)

            return result.astimezone(timezone.utc)

        except (TypeError, ValueError, OverflowError):
            logger.debug("Could not parse RSS date: %s", value)

    parsed = entry.get("published_parsed") or entry.get("updated_parsed")

    if parsed:
        try:
            return datetime(*parsed[:6], tzinfo=timezone.utc)

        except (TypeError, ValueError, OverflowError):
            logger.debug("Could not parse structured RSS date")

    return None


def make_slug(title: str) -> str:
    """Create a URL-friendly slug while preserving Telugu characters."""
    value = unicodedata.normalize(
        "NFKC",
        clean_text(title),
    ).lower()

    value = re.sub(r"[^\w\s-]", "", value, flags=re.UNICODE)
    value = re.sub(r"[\s_-]+", "-", value).strip("-")

    return value[:220].rstrip("-") or "news"


def unique_slug(title: str) -> str:
    """Generate a unique slug using the existing Article table."""
    base = make_slug(title)
    slug = base
    counter = 2

    while Article.query.filter_by(slug=slug).first() is not None:
        suffix = f"-{counter}"
        slug = f"{base[:220 - len(suffix)].rstrip('-')}{suffix}"
        counter += 1

    return slug


# ============================================================
# DATABASE CATEGORY HELPERS
# ============================================================

def get_category_by_name(name_en: str) -> Category | None:
    """Find an existing category by its English name."""
    return Category.query.filter_by(name_en=name_en).first()


def get_default_category() -> Category | None:
    """Use the existing National category as the fallback."""
    category = get_category_by_name("National")

    if category is None:
        logger.error(
            "The required fallback category 'National' is missing."
        )

    return category


def classify_category(
    title: str,
    summary: str = "",
    body: str = "",
) -> Category | None:
    """
    Classify an article using its headline first.

    Uses existing database categories.
    Does not create categories automatically.
    """

    title_text = normalize_for_matching(title)
    summary_text = normalize_for_matching(summary)
    body_text = normalize_for_matching(body)

    if not title_text and not summary_text and not body_text:
        return get_default_category()

    # Give distinctive headline subjects priority.
    headline_rules = (
        (
            "Business",
            (
                "global markets", "stock market", "share market",
                "sensex", "nifty", "stock prices", "market rally",
                "market crash", "economic growth", "inflation",
                "interest rates", "company earnings",
                "quarterly results", "business deal",
                "merger", "acquisition", "revenue growth",
                "profit rises", "profit falls", "gold prices",
                "silver prices", "crude oil prices", "oil prices",
                "ప్రపంచ మార్కెట్లు", "స్టాక్ మార్కెట్",
                "షేర్ మార్కెట్", "సెన్సెక్స్", "నిఫ్టీ",
                "ద్రవ్యోల్బణం", "వడ్డీ రేట్లు",
                "కంపెనీ లాభాలు", "బంగారం ధరలు",
                "వెండి ధరలు", "చమురు ధరలు",
            ),
        ),
        (
            "Sports",
            (
                "cricket", "ipl", "football", "tennis",
                "టీమిండియా", "క్రికెట్", "అర్ష్‌దీప్",
                "శ్రేయస్ అయ్యర్", "ఐపీఎల్", "ప్రపంచకప్",
                "ఫుట్‌బాల్", "టెన్నిస్", "ఒలింపిక్స్",
            ),
        ),
        (
            "Entertainment",
            (
                "movie review", "film review", "upcoming movie",
                "movie release", "actor", "actress", "cinema",
                "జయలలిత", "త్రిష", "త్రిషా", "కోలీవుడ్",
                "సినిమా", "సినీ", "నటి", "నటుడు",
                "హీరోయిన్", "మూవీ రివ్యూ", "ఓటీటీ",
            ),
        ),
        (
            "Technology",
            (
                "artificial intelligence", "cyber attack",
                "data leak", "iphone", "smartphone",
                "software update", "ఐఫోన్", "డేటా లీక్",
                "సైబర్ దాడి", "టెక్నాలజీ",
                "కృత్రిమ మేధస్సు", "స్మార్ట్‌ఫోన్",
            ),
        ),
        (
            "World",
            (
                "united states", "donald trump", "white house",
                "venezuela", "international relations",
                "foreign policy", "global conflict",
                "వెనిజులా", "అంతర్జాతీయ", "విదేశీ వ్యవహారాలు",
                "ప్రపంచ రాజకీయాలు", "విదేశాంగ శాఖ",
            ),
        ),
        (
            "Telangana",
            (
                "telangana", "hyderabad", "revanth reddy",
                "kcr", "ktr", "mancherial", "bellampalli",
                "తెలంగాణ", "హైదరాబాద్", "రేవంత్ రెడ్డి",
                "కేసీఆర్", "కేటీఆర్", "మంచిర్యాల",
                "బెల్లంపల్లి",
            ),
        ),
    )

    for category_name, keywords in headline_rules:
        if any(
            normalize_for_matching(keyword) in title_text
            for keyword in keywords
        ):
            category = get_category_by_name(category_name)

            if category is not None:
                return category

    # Score headline matches before examining the article body.
    title_scores = {}

    for category_name, keywords in CATEGORY_KEYWORDS.items():
        title_scores[category_name] = sum(
            1
            for keyword in keywords
            if normalize_for_matching(keyword) in title_text
        )

    highest_title_score = max(title_scores.values(), default=0)

    if highest_title_score > 0:
        selected_name = next(
            (
                name
                for name in CATEGORY_PRIORITY
                if title_scores.get(name, 0) == highest_title_score
            ),
            "National",
        )

        category = get_category_by_name(selected_name)

        if category is not None:
            return category

    # Other Indian states default to National unless a distinctive
    # subject has already matched above.
    if any(
        normalize_for_matching(keyword) in title_text
        for keyword in INDIAN_STATE_KEYWORDS
    ):
        category = get_category_by_name("National")

        if category is not None:
            return category

    # Use summary and body as supporting evidence.
    scores = {}

    for category_name, keywords in CATEGORY_KEYWORDS.items():
        summary_score = 0
        body_score = 0

        for keyword in keywords:
            phrase = normalize_for_matching(keyword)

            if not phrase:
                continue

            if phrase in summary_text:
                summary_score += 2

            if phrase in body_text:
                body_score += 1

        scores[category_name] = (
            min(summary_score, 8) + min(body_score, 5)
        )

    highest_score = max(scores.values(), default=0)

    if highest_score == 0:
        selected_name = "National"
    else:
        selected_name = next(
            (
                name
                for name in CATEGORY_PRIORITY
                if scores.get(name, 0) == highest_score
            ),
            "National",
        )

    category = get_category_by_name(selected_name)

    if category is None:
        logger.warning(
            "Category %r does not exist in the database.",
            selected_name,
        )
        category = get_default_category()

    return category


# ============================================================
# AUTHOR HELPERS
# ============================================================

def get_author() -> User | None:
    """Find an active admin, then an active editor."""
    admin = (
        User.query.filter(
            User.active.is_(True),
            User.role == "admin",
        )
        .order_by(User.id.asc())
        .first()
    )

    if admin:
        return admin

    return (
        User.query.filter(
            User.active.is_(True),
            User.role == "editor",
        )
        .order_by(User.id.asc())
        .first()
    )


# ============================================================
# RSS METADATA HELPERS
# ============================================================

def get_image_url(entry) -> str | None:
    """Extract a valid image URL from RSS metadata."""

    for item in entry.get("media_content", []) or []:
        image_url = clean_text(item.get("url"))

        if not image_url:
            continue

        media_type = clean_text(item.get("medium"))

        if media_type and media_type != "image":
            continue

        normalized = normalize_source_url(image_url)

        if normalized:
            return normalized[:MAX_SOURCE_URL_LENGTH]

    for item in entry.get("media_thumbnail", []) or []:
        image_url = clean_text(item.get("url"))

        if image_url:
            normalized = normalize_source_url(image_url)

            if normalized:
                return normalized[:MAX_SOURCE_URL_LENGTH]

    for item in entry.get("links", []) or []:
        if item.get("rel") != "enclosure":
            continue

        media_type = clean_text(item.get("type"))

        if media_type.startswith("image/"):
            normalized = normalize_source_url(
                clean_text(item.get("href"))
            )

            if normalized:
                return normalized[:MAX_SOURCE_URL_LENGTH]

    return None


def get_source_name(entry, feed) -> str:
    """Determine the source publisher name."""
    source = entry.get("source") or {}

    source_name = (
        clean_text(source.get("title"))
        or clean_text(feed.get("title"))
    )

    if not source_name:
        source_url = normalize_source_url(entry.get("link", ""))

        try:
            source_name = (
                urlparse(source_url).hostname or "Unknown source"
            )
        except ValueError:
            source_name = "Unknown source"

    return source_name[:200]


def get_rss_summary(entry) -> str:
    """Extract a summary from an RSS entry."""
    return clean_text(
        entry.get("summary") or entry.get("description")
    )


# ============================================================
# COLLECT ONE RSS FEED
# ============================================================

def collect_feed(feed_url: str, dry_run: bool = False) -> int:
    """
    Collect one RSS feed.

    dry_run=True:
        Checks and previews eligible articles without saving them.

    dry_run=False:
        Saves eligible articles as drafts.

    Articles are never automatically published.
    """

    feed_url = normalize_source_url(feed_url)

    if not feed_url:
        logger.error("Invalid RSS feed URL.")
        return 0

    try:
        feed = feedparser.parse(
            feed_url,
            request_headers={
                "User-Agent": "VSTV6NewsCollector/1.0",
            },
        )
    except Exception:
        logger.exception("Could not parse RSS feed: %s", feed_url)
        return 0

    if getattr(feed, "bozo", False):
        logger.warning(
            "RSS parsing warning for %s: %s",
            feed_url,
            getattr(feed, "bozo_exception", "Unknown error"),
        )

    if not getattr(feed, "entries", None):
        logger.warning("RSS feed has no entries: %s", feed_url)
        return 0

    saved_count = 0

    for entry in feed.entries:
        source_url = normalize_source_url(entry.get("link", ""))
        title = clean_text(entry.get("title"))

        if not title or not source_url:
            logger.warning("Skipping entry without valid title or URL.")
            continue

        try:
            # Check duplicates.
            existing = Article.query.filter_by(
                source_url=source_url
            ).first()

            if existing:
                logger.debug("Skipping duplicate: %s", source_url)
                continue

            # Extract article text.
            extracted_text = clean_article_body(
                extract_article_text(source_url)
            )

            if len(extracted_text) < MINIMUM_ARTICLE_LENGTH:
                logger.info(
                    "Skipping short article: %s (%s characters)",
                    source_url,
                    len(extracted_text),
                )
                continue

            rss_summary = get_rss_summary(entry)

            # Detect language.
            language = detect_language(
                title=title,
                summary=rss_summary,
                body=extracted_text,
            )

            if language != "te":
                logger.info(
                    "Skipping non-Telugu article: %s",
                    source_url,
                )
                continue

            if not contains_telugu_script(title) or not contains_telugu_script(extracted_text):
                logger.info(
                    "Skipping article without a Telugu headline and body: %s",
                    source_url,
                )
                continue

            # Classify category.
            category = classify_category(
                title=title,
                summary=rss_summary,
                body=extracted_text,
            )

            if category is None:
                logger.error("No category found: %s", source_url)
                continue

            # Preview mode: no database writes.
            if dry_run:
                logger.info(
                    "[DRY RUN] WOULD SAVE AS DRAFT | "
                    "Language: %s | Category: %s | "
                    "Title: %s | Characters: %s | URL: %s",
                    language,
                    category.name_en,
                    title,
                    len(extracted_text),
                    source_url,
                )

                saved_count += 1
                continue

            # Find the author only when saving.
            author = get_author()

            if author is None:
                logger.error(
                    "No active administrator or editor exists. "
                    "Create an active user before collecting news."
                )

                db.session.rollback()
                return saved_count

            summary_text = rss_summary or extracted_text[:450]
            summary_te = (
                rss_summary
                if is_telugu_summary(rss_summary)
                else None
            )

            # Telugu content stored in _en fields is not translated.
            # This mapping preserves the existing Article model.
            if language == "te":
                article = Article(
                    title_en=title[:MAX_TITLE_LENGTH],
                    title_te=title[:MAX_TITLE_LENGTH],
                    slug=unique_slug(title),
                    summary_en=summary_text[:MAX_SUMMARY_LENGTH],
                    summary_te=(
                        summary_te[:MAX_SUMMARY_LENGTH]
                        if summary_te
                        else None
                    ),
                    body_en=extracted_text,
                    body_te=extracted_text,
                    language="te",
                )
            else:
                article = Article(
                    title_en=title[:MAX_TITLE_LENGTH],
                    title_te=None,
                    slug=unique_slug(title),
                    summary_en=summary_text[:MAX_SUMMARY_LENGTH],
                    summary_te=None,
                    body_en=extracted_text,
                    body_te=None,
                    language="en",
                )

            # Common database fields.
            article.category_id = category.id
            article.author_id = author.id
            article.source_name = get_source_name(entry, feed)
            article.source_url = source_url
            article.image_url = get_image_url(entry)

            # Always create drafts, never auto-publish.
            article.status = "draft"
            article.published_at = parse_published_date(entry)

            db.session.add(article)
            db.session.commit()

            saved_count += 1

            logger.info(
                "Saved draft | Language: %s | Category: %s | "
                "Title: %s | Characters: %s",
                article.language,
                category.name_en,
                article.title_en,
                len(extracted_text),
            )

        except Exception:
            db.session.rollback()

            logger.exception(
                "Failed to collect RSS entry: %s",
                source_url,
            )

    logger.info(
        "Finished feed %s: %s eligible articles %s",
        feed_url,
        saved_count,
        "previewed" if dry_run else "saved as drafts",
    )

    return saved_count


# ============================================================
# COLLECT ALL RSS FEEDS
# ============================================================

def collect_all_feeds(dry_run: bool = False) -> int:
    """Collect or preview all RSS feeds configured in .env."""

    if not RSS_FEEDS:
        logger.error(
            "RSS_FEEDS is empty or missing from the environment."
        )
        return 0

    total_count = 0

    for feed_url in RSS_FEEDS:
        try:
            total_count += collect_feed(
                feed_url,
                dry_run=dry_run,
            )

        except Exception:
            db.session.rollback()

            logger.exception(
                "Failed to process RSS feed: %s",
                feed_url,
            )

    if dry_run:
        logger.info(
            "RSS DRY RUN COMPLETE: %s eligible article(s) previewed. "
            "No articles were saved.",
            total_count,
        )
    else:
        logger.info(
            "RSS collection completed. New drafts saved: %s",
            total_count,
        )

    return total_count


# ============================================================
# BACKWARD-COMPATIBLE FUNCTION ALIASES
# ============================================================

def collect_feeds(dry_run: bool = False) -> int:
    """Compatibility alias for existing application routes."""
    return collect_all_feeds(dry_run=dry_run)