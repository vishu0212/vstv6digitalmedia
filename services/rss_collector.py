import os
import re
import hashlib
import logging

from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from html import unescape
from urllib.parse import (
    urlparse,
    urldefrag,
    parse_qsl,
    urlencode,
    urlunparse,
)

import feedparser
import requests
from dotenv import load_dotenv

load_dotenv()

logger = logging.getLogger(__name__)

# ============================================================
# 1. CONFIGURATION
# ============================================================

RSS_FEEDS = [
    url.strip()
    for url in os.getenv("RSS_FEEDS", "").split(",")
    if url.strip()
]

REQUEST_TIMEOUT = (5, 20)
DEFAULT_LIMIT_PER_FEED = 30

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 Chrome/130.0 Safari/537.36"
)

# Set RSS_MAX_AGE_DAYS=7 in .env to collect recent articles only.
# Set RSS_MAX_AGE_DAYS=0 to disable the age filter.
RSS_MAX_AGE_DAYS = int(os.getenv("RSS_MAX_AGE_DAYS", "7"))

# ============================================================
# 2. MANCHERIAL DISTRICT KEYWORDS
# ============================================================

LOCAL_KEYWORDS = [
    "మంచిర్యాల",
    "మంచిర్యాల జిల్లా",
    "mancherial",
    "బెల్లంపల్లి",
    "bellampalli",
    "bellampalle",
    "mandamarri",
    "మందమర్రి",
    "lakshettipet",
    "laxettipet",
    "లక్షెట్టిపేట",
    "లక్సెట్టిపేట",
    "chennur",
    "చెన్నూరు",
    "nasapur",
    "నస్పూర్",
    "hajipur",
    "హాజీపూర్",
    "jannaram",
    "జన్నారం",
    "kasipet",
    "కాసిపేట",
    "tandur",
    "తాండూర్",
    "nennel",
    "నెన్నెల",
    "vemanpally",
    "వేమనపల్లి",
    "dandepalli",
    "దండేపల్లి",
    "bheemini",
    "భీమిని",
]

# ============================================================
# 3. TELANGANA KEYWORDS
# ============================================================

TELANGANA_KEYWORDS = [
    "తెలంగాణ",
    "తెలంగాణలో",
    "తెలంగాణకు",
    "హైదరాబాద్",
    "సికింద్రాబాద్",
    "వరంగల్",
    "కరీంనగర్",
    "ఖమ్మం",
    "నిజామాబాద్",
    "ఆదిలాబాద్",
    "పెద్దపల్లి",
    "సిద్దిపేట",
    "నల్గొండ",
    "మహబూబ్‌నగర్",
    "సూర్యాపేట",
    "జగిత్యాల",
    "భూపాలపల్లి",
    "భద్రాద్రి",
    "కొత్తగూడెం",
    "జనగామ",
    "ములుగు",
    "మెదక్",
    "మేడ్చల్",
    "రంగారెడ్డి",
    "వనపర్తి",
    "నారాయణపేట",
    "గద్వాల",
    "కామారెడ్డి",
    "నిర్మల్",
    "telangana",
    "hyderabad",
    "secunderabad",
    "warangal",
    "karimnagar",
    "khammam",
    "nizamabad",
    "adilabad",
    "peddapalli",
    "siddipet",
    "nalgonda",
    "mahabubnagar",
    "suryapet",
    "jagtial",
    "bhupalpally",
    "bhadradri",
    "kothagudem",
    "janagaon",
    "mulugu",
    "medak",
    "medchal",
    "rangareddy",
    "wanaparthy",
    "narayanpet",
    "gadwal",
    "kamareddy",
    "nirmal",
]

# ============================================================
# 4. NEWS CATEGORY KEYWORDS
# ============================================================

CATEGORY_KEYWORDS = {
    "education_jobs": [
        "ఉద్యోగం",
        "ఉద్యోగాలు",
        "జాబ్స్",
        "నోటిఫికేషన్",
        "పరీక్ష",
        "ఫలితాలు",
        "నియామకాలు",
        "విద్యార్థులు",
        "అడ్మిషన్",
        "ఉపాధ్యాయ",
        "ఉపాధి",
        "jobs",
        "education",
        "exam",
        "results",
        "recruitment",
        "admission",
        "notification",
        "neet",
        "jee",
        "tet",
        "gds recruitment",
    ],
    "politics": [
        "రాజకీయ",
        "ఎన్నికలు",
        "మంత్రి",
        "ముఖ్యమంత్రి",
        "ప్రభుత్వం",
        "పార్టీ",
        "ఎమ్మెల్యే",
        "ఎంపీ",
        "రాజీనామా",
        "politics",
        "election",
        "minister",
        "chief minister",
        "government",
        "mla",
        "mp ",
    ],
    "sports": [
        "క్రికెట్",
        "క్రికెటర్",
        "టీమిండియా",
        "క్రీడలు",
        "ఫుట్‌బాల్",
        "cricket",
        "sports",
        "football",
        "tennis",
        "olympics",
    ],
    "entertainment": [
        "సినిమా",
        "సినిమాలు",
        "టాలీవుడ్",
        "హీరో",
        "హీరోయిన్",
        "సినీ",
        "వినోదం",
        "ట్రైలర్",
        "movie",
        "cinema",
        "tollywood",
        "entertainment",
        "trailer",
    ],
    "technology": [
        "టెక్నాలజీ",
        "ఏఐ",
        "కృత్రిమ మేధస్సు",
        "సాంకేతిక",
        "మొబైల్",
        "సాఫ్ట్‌వేర్",
        "technology",
        "artificial intelligence",
        "software",
        "mobile",
        "gadget",
    ],
    "agriculture": [
        "రైతు",
        "రైతులు",
        "వ్యవసాయం",
        "పంట",
        "విత్తనాలు",
        "రైతు భరోసా",
        "సాగు",
        "ధాన్యం",
        "farmer",
        "agriculture",
        "crop",
        "farming",
    ],
    "crime": [
        "పోలీసులు",
        "అరెస్ట్",
        "నేరం",
        "హత్య",
        "దొంగతనం",
        "ప్రమాదం",
        "కేసు నమోదు",
        "లంచం",
        "అవినీతి",
        "police",
        "arrest",
        "crime",
        "murder",
        "accident",
        "corruption",
    ],
    "health": [
        "ఆరోగ్యం",
        "వైద్యం",
        "ఆసుపత్రి",
        "వైద్యులు",
        "డాక్టర్లు",
        "వ్యాధి",
        "ఆరోగ్యశాఖ",
        "health",
        "hospital",
        "doctor",
        "medical",
        "disease",
    ],
}

VALID_REGIONS = {
    "local",
    "telangana",
    "national",
}

VALID_CATEGORIES = set(CATEGORY_KEYWORDS) | {"general"}

# ============================================================
# 5. TEXT HELPERS
# ============================================================


def normalize_text(value):
    """Normalize text for keyword comparisons."""
    value = unescape(str(value or "")).casefold()
    return re.sub(r"\s+", " ", value).strip()


def clean_html(value):
    """Remove HTML markup from RSS titles and summaries."""
    value = unescape(str(value or ""))

    value = re.sub(
        r"(?is)<(script|style).*?>.*?</\1>",
        " ",
        value,
    )

    value = re.sub(r"(?s)<[^>]+>", " ", value)
    value = re.sub(r"\s+", " ", value)

    return value.strip()


def is_telugu_text(value):
    """Check whether text contains Telugu Unicode characters."""
    return bool(re.search(r"[\u0C00-\u0C7F]", str(value or "")))


def contains_keyword(text, keywords):
    """Return True when any keyword is found."""
    text = normalize_text(text)

    for keyword in keywords:
        keyword = normalize_text(keyword)

        if not keyword:
            continue

        # English keywords use word boundaries to avoid matches
        # inside unrelated words. Telugu uses substring matching.
        if re.search(r"[\u0C00-\u0C7F]", keyword):
            if keyword in text:
                return True
        else:
            pattern = r"(?<![a-z0-9])" + re.escape(keyword)
            pattern += r"(?![a-z0-9])"

            if re.search(pattern, text):
                return True

    return False


# ============================================================
# 6. REGION CLASSIFICATION
# ============================================================


def detect_region(title, summary=""):
    """
    Return local, telangana, or national.

    Classification is based on the title and summary, not the RSS URL.
    This is keyword-based and should be reviewed before publication.
    """
    text = normalize_text(f"{title} {summary}")

    # Specific Mancherial district locations take priority.
    if contains_keyword(text, LOCAL_KEYWORDS):
        return "local"

    if contains_keyword(text, TELANGANA_KEYWORDS):
        return "telangana"

    return "national"


# ============================================================
# 7. CATEGORY CLASSIFICATION
# ============================================================


def get_category(title, summary=""):
    """Assign a category to the article."""
    text = normalize_text(f"{title} {summary}")

    priority = [
        "education_jobs",
        "crime",
        "agriculture",
        "health",
        "politics",
        "sports",
        "entertainment",
        "technology",
    ]

    for category in priority:
        if contains_keyword(
            text,
            CATEGORY_KEYWORDS[category],
        ):
            return category

    return "general"


# ============================================================
# 8. SOURCE HELPERS
# ============================================================


def get_source_name(parsed_feed, feed_url):
    """Get the source name from the RSS feed metadata."""
    source_name = clean_html(
        parsed_feed.feed.get("title", "")
    )

    if source_name:
        return source_name

    return urlparse(feed_url).netloc.removeprefix("www.")


def get_article_date(entry):
    """Convert an RSS publication date to a UTC ISO timestamp."""
    for key in ("published", "updated", "created"):
        raw_date = entry.get(key)

        if not raw_date:
            continue

        try:
            date_value = parsedate_to_datetime(raw_date)

            if date_value.tzinfo is None:
                date_value = date_value.replace(
                    tzinfo=timezone.utc
                )

            return date_value.astimezone(
                timezone.utc
            ).isoformat()

        except (TypeError, ValueError, OverflowError):
            continue

    for key in ("published_parsed", "updated_parsed"):
        parsed_date = entry.get(key)

        if not parsed_date:
            continue

        try:
            from calendar import timegm

            return datetime.fromtimestamp(
                timegm(parsed_date),
                tz=timezone.utc,
            ).isoformat()

        except (TypeError, ValueError, OverflowError, OSError):
            continue

    return None


# ============================================================
# 9. DEDUPLICATION
# ============================================================


def get_article_id(title, link):
    """Generate a stable identifier for duplicate detection."""
    link = urldefrag(str(link or "").strip())[0]

    if link:
        parts = urlparse(link)

        tracking_names = {
            "fbclid",
            "gclid",
            "ref",
            "referrer",
        }

        query_items = [
            (key, value)
            for key, value in parse_qsl(
                parts.query,
                keep_blank_values=True,
            )
            if key.lower() not in tracking_names
            and not key.lower().startswith("utm_")
        ]

        link = urlunparse(
            parts._replace(
                query=urlencode(query_items),
                fragment="",
            )
        ).rstrip("/")

    identity = link or normalize_text(title)

    return hashlib.sha256(
        identity.encode("utf-8")
    ).hexdigest()


# ============================================================
# 10. PUBLICATION DATE FILTER
# ============================================================


def is_recent_article(published_at, max_age_days=7):
    """
    Check whether an article is recent.

    Unknown dates are retained to avoid silently discarding
    potentially useful local news.
    """
    if max_age_days <= 0 or not published_at:
        return True

    try:
        article_date = datetime.fromisoformat(
            published_at.replace("Z", "+00:00")
        )

        if article_date.tzinfo is None:
            article_date = article_date.replace(
                tzinfo=timezone.utc
            )

        current_time = datetime.now(timezone.utc)
        oldest_allowed = current_time - timedelta(
            days=max_age_days
        )

        return oldest_allowed <= article_date <= current_time

    except (TypeError, ValueError, OverflowError):
        return True


# ============================================================
# 11. MAIN RSS COLLECTOR
# ============================================================


def collect_rss_news(
    feeds=None,
    limit_per_feed=30,
    telugu_only=False,
    region=None,
    category=None,
    max_age_days=None,
):
    """
    Collect RSS articles for VSTV6 Digital Media.

    Existing dictionary keys are preserved:
        article_id, title, summary, link, source_name,
        source_feed, published_at, category, region, language

    Filters:
        region='local'
        region='telangana'
        region='national'
        category='education_jobs'
        telugu_only=True
        max_age_days=7
    """
    feeds = feeds if feeds is not None else RSS_FEEDS

    if isinstance(feeds, str):
        feeds = [feeds]

    if limit_per_feed < 1:
        raise ValueError("limit_per_feed must be at least 1.")

    if region and region not in VALID_REGIONS:
        raise ValueError(
            f"Invalid region {region!r}. "
            f"Valid values: {sorted(VALID_REGIONS)}"
        )

    if category and category not in VALID_CATEGORIES:
        raise ValueError(
            f"Invalid category {category!r}. "
            f"Valid values: {sorted(VALID_CATEGORIES)}"
        )

    if max_age_days is None:
        max_age_days = RSS_MAX_AGE_DAYS

    if not feeds:
        logger.warning("No RSS feeds configured in RSS_FEEDS.")
        return []

    articles = []
    seen_ids = set()

    headers = {
        "User-Agent": USER_AGENT,
        "Accept": (
            "application/rss+xml, application/atom+xml, "
            "application/xml, text/xml, */*"
        ),
    }

    with requests.Session() as session:
        session.headers.update(headers)

        for feed_url in feeds:
            print(f"\nFetching: {feed_url}")

            try:
                response = session.get(
                    feed_url,
                    timeout=REQUEST_TIMEOUT,
                )
                response.raise_for_status()

                parsed_feed = feedparser.parse(response.content)

                if not parsed_feed.entries:
                    print("WARNING: No RSS entries found.")
                    continue

                source_name = get_source_name(
                    parsed_feed,
                    feed_url,
                )

                added_count = 0
                skipped_count = 0

                for entry in parsed_feed.entries[:limit_per_feed]:
                    title = clean_html(
                        entry.get("title", "")
                    )

                    link = str(
                        entry.get("link", "")
                    ).strip()

                    if not title or not link:
                        skipped_count += 1
                        continue

                    parsed_link = urlparse(link)

                    if parsed_link.scheme not in {"http", "https"}:
                        skipped_count += 1
                        continue

                    summary = clean_html(
                        entry.get("summary")
                        or entry.get("description")
                        or ""
                    )

                    # Telugu headline filter.
                    if telugu_only and not is_telugu_text(title):
                        skipped_count += 1
                        continue

                    published_at = get_article_date(entry)

                    # Recent-news filter.
                    if not is_recent_article(
                        published_at,
                        max_age_days,
                    ):
                        skipped_count += 1
                        continue

                    article_id = get_article_id(
                        title,
                        link,
                    )

                    if article_id in seen_ids:
                        skipped_count += 1
                        continue

                    article_region = detect_region(
                        title,
                        summary,
                    )

                    article_category = get_category(
                        title,
                        summary,
                    )

                    if region and article_region != region:
                        skipped_count += 1
                        continue

                    if category and article_category != category:
                        skipped_count += 1
                        continue

                    seen_ids.add(article_id)

                    articles.append({
                        "article_id": article_id,
                        "title": title,
                        "summary": summary,
                        "link": link,
                        "source_name": source_name,
                        "source_feed": feed_url,
                        "published_at": published_at,
                        "category": article_category,
                        "region": article_region,
                        "language": (
                            "te"
                            if is_telugu_text(title)
                            else "other"
                        ),
                    })

                    added_count += 1

                print(
                    f"SUCCESS: {source_name} | "
                    f"Added: {added_count} | "
                    f"Skipped: {skipped_count}"
                )

            except requests.RequestException as error:
                logger.warning(
                    "Unable to fetch RSS feed %s: %s",
                    feed_url,
                    error,
                )
                print(f"FAILED: {error}")

            except Exception:
                logger.exception(
                    "Unexpected error while processing %s",
                    feed_url,
                )
                print("FAILED: Unexpected RSS processing error.")

    # Sort by region, then newest publication date first.
    region_priority = {
        "local": 0,
        "telangana": 1,
        "national": 2,
    }

    def sort_key(article):
        date_text = article.get("published_at")

        try:
            date_value = datetime.fromisoformat(
                date_text.replace("Z", "+00:00")
            )

            if date_value.tzinfo is None:
                date_value = date_value.replace(
                    tzinfo=timezone.utc
                )

            timestamp = date_value.timestamp()

        except (AttributeError, TypeError, ValueError, OverflowError):
            timestamp = 0

        return (
            region_priority.get(article["region"], 3),
            -timestamp,
        )

    articles.sort(key=sort_key)

    return articles


# ============================================================
# 12. COMMAND-LINE TESTING
# ============================================================


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    print("=" * 70)
    print("VSTV6 DIGITAL MEDIA")
    print("TELUGU RSS NEWS COLLECTOR")
    print("=" * 70)

    news = collect_rss_news(
        limit_per_feed=30,
        telugu_only=True,
    )

    print("\n" + "=" * 70)
    print("COLLECTION SUMMARY")
    print("=" * 70)

    print(f"Total matching articles: {len(news)}")

    for article in news[:30]:
        print(f"\n[{article['region'].upper()}]")
        print(f"వార్త: {article['title']}")
        print(f"వర్గం: {article['category']}")
        print(f"మూలం: {article['source_name']}")
        print(
            "ప్రచురణ తేదీ: "
            f"{article['published_at'] or 'తెలియదు'}"
        )
        print(f"లింక్: {article['link']}")