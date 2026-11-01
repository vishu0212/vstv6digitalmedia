"""
VSTV6 Digital Media — RSS News Collector

Features:
- Collects news from RSS feeds configured in .env
- Supports Telugu and English headlines
- Classifies local, Telangana, and national news
- Classifies news by category
- Removes duplicate articles
- Filters old articles
- Handles unavailable feeds without stopping the collector
- Prints collected news to the terminal

Dependencies:
    pip install feedparser requests python-dotenv
"""

import os
import re
import hashlib
import logging

from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from html import unescape
from urllib.parse import urlparse

import feedparser
import requests

from dotenv import load_dotenv


# ============================================================
# CONFIGURATION
# ============================================================

BASE_DIR = os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))
)

load_dotenv(os.path.join(BASE_DIR, ".env"))

MAX_AGE_DAYS = int(os.getenv("RSS_MAX_AGE_DAYS", "7"))
REQUEST_TIMEOUT = int(os.getenv("RSS_TIMEOUT", "20"))
DEFAULT_LIMIT_PER_FEED = int(
    os.getenv("RSS_LIMIT_PER_FEED", "30")
)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s: %(message)s",
)

logger = logging.getLogger(__name__)


# ============================================================
# RSS FEED CONFIGURATION
# ============================================================

def configured_feeds():
    """Read RSS feed URLs from the RSS_FEEDS environment variable."""
    raw_feeds = os.getenv("RSS_FEEDS", "")

    feeds = []

    for item in raw_feeds.split(","):
        url = item.strip()

        if not url:
            continue

        parsed = urlparse(url)

        if parsed.scheme not in {"http", "https"}:
            logger.warning("Skipping invalid feed URL: %s", url)
            continue

        if not parsed.netloc:
            logger.warning("Skipping malformed feed URL: %s", url)
            continue

        if url not in feeds:
            feeds.append(url)

    return feeds


# ============================================================
# TEXT CLEANING
# ============================================================

def normalize_text(value):
    """Normalize whitespace and HTML entities without damaging Telugu."""
    if not value:
        return ""

    value = unescape(str(value))
    value = re.sub(r"<[^>]+>", " ", value)
    value = value.replace("\xa0", " ")
    value = re.sub(r"\s+", " ", value)

    return value.strip()


def clean_html(value):
    """Remove HTML markup from RSS summaries."""
    if not value:
        return ""

    value = unescape(str(value))
    value = re.sub(
        r"(?is)<(script|style).*?>.*?</\1>",
        " ",
        value,
    )
    value = re.sub(r"(?s)<[^>]+>", " ", value)
    value = re.sub(r"\s+", " ", value)

    return value.strip()


def is_telugu_text(text):
    """Return True when Telugu Unicode characters occur in the text."""
    if not text:
        return False

    return bool(re.search(r"[\u0C00-\u0C7F]", text))


def contains_keyword(text, keywords):
    """
    Match Telugu keywords by substring.
    Match English keywords using word boundaries where possible.
    """
    if not text or not keywords:
        return False

    text = normalize_text(text).casefold()

    for keyword in keywords:
        keyword = normalize_text(keyword).casefold()

        if not keyword:
            continue

        # Telugu words can be embedded in longer Telugu text.
        if re.search(r"[\u0C00-\u0C7F]", keyword):
            if keyword in text:
                return True

        # English keywords are matched as whole words.
        else:
            pattern = (
                r"(?<![a-z0-9])"
                + re.escape(keyword)
                + r"(?![a-z0-9])"
            )

            if re.search(pattern, text):
                return True

    return False


# ============================================================
# LOCAL KEYWORDS — MANCHERIAL / BELLAMPALLI
# ============================================================

LOCAL_KEYWORDS = [
    "మంచిర్యాల",
    "బెల్లంపల్లి",
    "మందమర్రి",
    "లక్సెట్టిపేట",
    "చెన్నూర్",
    "కోటపల్లి",
    "నస్పూర్",
    "హాజీపూర్",
    "జైపూర్",
    "దండేపల్లి",
    "తాండూర్",
    "కాసిపేట",
    "భీమారం",
    "వేమనపల్లి",
    "కన్నెపల్లి",
    "మంచిర్యాల జిల్లా",
    "Mancherial",
    "Bellampalli",
    "Bellampalle",
    "Mandamarri",
    "Luxettipet",
    "Chennur",
    "Kotapalli",
    "Naspur",
    "Hajipur",
    "Jaipur",
    "Dandepalli",
    "Tandur",
    "Kasipet",
    "Vemanpalli",
]


# ============================================================
# TELANGANA KEYWORDS
# ============================================================

TELANGANA_KEYWORDS = [
    "తెలంగాణ",
    "హైదరాబాద్",
    "హైదరాబాద్‌లో",
    "వరంగల్",
    "కరీంనగర్",
    "ఖమ్మం",
    "నిజామాబాద్",
    "ఆదిలాబాద్",
    "నల్గొండ",
    "సూర్యాపేట",
    "సిద్దిపేట",
    "సంగారెడ్డి",
    "మహబూబ్‌నగర్",
    "రంగారెడ్డి",
    "మేడ్చల్",
    "జగిత్యాల",
    "పెద్దపల్లి",
    "రామగుండం",
    "జనగామ",
    "భద్రాద్రి",
    "కొత్తగూడెం",
    "వనపర్తి",
    "నాగర్‌కర్నూల్",
    "జయశంకర్ భూపాలపల్లి",
    "ములుగు",
    "నారాయణపేట",
    "యాదాద్రి",
    "కామారెడ్డి",
    "నిర్మల్",
    "రాజన్న సిరిసిల్ల",
    "వికారాబాద్",
    "మెదక్",
    "మహబూబాబాద్",
    "హనుమకొండ",
    "తెలంగాణ ప్రభుత్వం",
    "తెలంగాణ సీఎం",
    "తెలంగాణ ముఖ్యమంత్రి",
    "Telangana",
    "Hyderabad",
    "Warangal",
    "Karimnagar",
    "Khammam",
    "Nizamabad",
    "Adilabad",
    "Nalgonda",
    "Suryapet",
    "Siddipet",
    "Sangareddy",
    "Mahabubnagar",
    "Rangareddy",
    "Medchal",
    "Jagtial",
    "Peddapalli",
    "Ramagundam",
    "Bhadradri",
    "Kothagudem",
    "Wanaparthy",
    "Nagarkurnool",
    "Mulugu",
    "Nirmal",
    "Medak",
]


# ============================================================
# CATEGORY KEYWORDS
# ============================================================

CATEGORY_KEYWORDS = {
    "education_jobs": [
        "ఉద్యోగాలు",
        "ఉద్యోగం",
        "నియామకాలు",
        "నోటిఫికేషన్",
        "పరీక్షలు",
        "ఫలితాలు",
        "హాల్ టికెట్",
        "హాల్‌టికెట్",
        "విద్యార్థులు",
        "విద్య",
        "పాఠశాల",
        "కాలేజీ",
        "యూనివర్సిటీ",
        "టీచర్",
        "డీఎస్సీ",
        "టెట్",
        "గ్రూప్స్",
        "జాబ్స్",
        "రిక్రూట్మెంట్",
        "నోటిఫికేషన్లు",
        "పరీక్ష ఫలితాలు",
        "scholarship",
        "recruitment",
        "notification",
        "exam",
        "exams",
        "results",
        "hall ticket",
        "education",
        "students",
        "school",
        "college",
        "university",
        "teacher",
        "jobs",
        "job alert",
        "vacancy",
        "vacancies",
        "government jobs",
        "admit card",
    ],

    "sports": [
        "క్రికెట్",
        "క్రికెటర్",
        "ఫుట్‌బాల్",
        "ఫుట్బాల్",
        "హాకీ",
        "టెన్నిస్",
        "కబడ్డీ",
        "ఐపీఎల్",
        "ప్రపంచకప్",
        "ప్రపంచ కప్",
        "వన్డే",
        "టీ20",
        "టెస్ట్ మ్యాచ్",
        "విరాట్ కోహ్లీ",
        "రోహిత్ శర్మ",
        "శుభ్‌మన్ గిల్",
        "టీమిండియా",
        "భారత్ జట్టు",
        "క్రీడలు",
        "మ్యాచ్",
        "ఆటగాడు",
        "ఆటగాళ్లు",
        "ఫైనల్ మ్యాచ్",
        "ఒలింపిక్స్",
        "cricket",
        "cricketer",
        "football",
        "hockey",
        "tennis",
        "kabaddi",
        "ipl",
        "world cup",
        "t20",
        "odi",
        "test match",
        "team india",
        "virat kohli",
        "rohit sharma",
        "sports",
        "match",
        "player",
        "players",
        "olympics",
        "badminton",
        "wrestling",
        "championship",
    ],

    "crime": [
        "హత్య",
        "హత్యలు",
        "దొంగతనం",
        "దోపిడీ",
        "అరెస్ట్",
        "అరెస్టు",
        "పోలీసులు",
        "పోలీస్",
        "కిడ్నాప్",
        "అపహరణ",
        "మోసం",
        "సైబర్ క్రైమ్",
        "సైబర్ నేరం",
        "అత్యాచారం",
        "దాడి",
        "కాల్పులు",
        "ప్రమాదం",
        "అక్రమ రవాణా",
        "డ్రగ్స్",
        "లంచం",
        "నేరం",
        "నేరస్థుడు",
        "కేసు నమోదు",
        "చోరీ",
        "accident",
        "murder",
        "robbery",
        "theft",
        "arrest",
        "police",
        "kidnap",
        "kidnapping",
        "fraud",
        "cyber crime",
        "rape",
        "attack",
        "shooting",
        "drugs",
        "bribery",
        "crime",
        "criminal",
        "case filed",
    ],

    "agriculture": [
        "రైతులు",
        "రైతు",
        "వ్యవసాయం",
        "పంటలు",
        "పంట",
        "వరి",
        "ధాన్యం",
        "మొక్కజొన్న",
        "పత్తి",
        "మిర్చి",
        "రైతు బంధు",
        "రైతు భరోసా",
        "రుణమాఫీ",
        "ఎరువులు",
        "విత్తనాలు",
        "సాగు",
        "పంట నష్టం",
        "వ్యవసాయ శాఖ",
        "ధాన్యం కొనుగోలు",
        "రైతు సమస్యలు",
        "రైతు బీమా",
        "agriculture",
        "farmer",
        "farmers",
        "crop",
        "crops",
        "paddy",
        "rice",
        "cotton",
        "maize",
        "fertilizer",
        "fertilizers",
        "seeds",
        "harvest",
        "crop damage",
        "farm loan",
        "loan waiver",
        "irrigation",
    ],

    "health": [
        "ఆరోగ్యం",
        "వైద్యం",
        "ఆసుపత్రి",
        "హాస్పిటల్",
        "డాక్టర్",
        "వైద్యులు",
        "వ్యాధి",
        "జ్వరం",
        "డెంగ్యూ",
        "మలేరియా",
        "వైరస్",
        "కరోనా",
        "కోవిడ్",
        "ఆరోగ్య శాఖ",
        "చికిత్స",
        "మరణాలు",
        "టీకా",
        "రక్తదానం",
        "ambulance",
        "health",
        "hospital",
        "doctor",
        "disease",
        "fever",
        "dengue",
        "malaria",
        "virus",
        "covid",
        "coronavirus",
        "medical",
        "treatment",
        "vaccine",
        "healthcare",
        "blood donation",
    ],

    "politics": [
        "రాజకీయాలు",
        "రాజకీయ",
        "ఎన్నికలు",
        "ఎన్నికల",
        "ముఖ్యమంత్రి",
        "ప్రధానమంత్రి",
        "మంత్రి",
        "మంత్రివర్గం",
        "ప్రభుత్వం",
        "ప్రతిపక్షం",
        "పార్లమెంట్",
        "అసెంబ్లీ",
        "లోక్‌సభ",
        "రాజ్యసభ",
        "కాంగ్రెస్",
        "బీజేపీ",
        "బిఆర్ఎస్",
        "బీఆర్ఎస్",
        "బీఆర్ఎస్",
        "బీఆర్ఎస్ పార్టీ",
        "రేవంత్ రెడ్డి",
        "కేసీఆర్",
        "కేటీఆర్",
        "రాహుల్ గాంధీ",
        "మోదీ",
        "నరేంద్ర మోదీ",
        "పార్టీ",
        "ఎమ్మెల్యే",
        "ఎంపీ",
        "పాలన",
        "రాజకీయ నాయకుడు",
        "politics",
        "election",
        "elections",
        "chief minister",
        "prime minister",
        "minister",
        "government",
        "opposition",
        "parliament",
        "assembly",
        "congress",
        "bjp",
        "brs",
        "rahul gandhi",
        "narendra modi",
        "revanth reddy",
        "kcr",
        "ktr",
        "mla",
        "mp",
        "political party",
    ],

    "entertainment": [
        "సినిమా",
        "సినిమాలు",
        "సినీ",
        "నటుడు",
        "నటి",
        "హీరో",
        "హీరోయిన్",
        "దర్శకుడు",
        "టాలీవుడ్",
        "బాలీవుడ్",
        "పాట",
        "సంగీతం",
        "ట్రైలర్",
        "టీజర్",
        "విడుదల",
        "బాక్సాఫీస్",
        "సినీ పరిశ్రమ",
        "వెబ్ సిరీస్",
        "సెలబ్రిటీ",
        "సెలబ్రిటీల",
        "movie",
        "movies",
        "cinema",
        "actor",
        "actress",
        "hero",
        "heroine",
        "director",
        "tollywood",
        "bollywood",
        "song",
        "music",
        "trailer",
        "teaser",
        "box office",
        "web series",
        "celebrity",
        "film industry",
    ],

    "technology": [
        "సాంకేతికత",
        "టెక్నాలజీ",
        "కృత్రిమ మేధస్సు",
        "ఏఐ",
        "ఆర్టిఫిషియల్ ఇంటెలిజెన్స్",
        "మొబైల్",
        "స్మార్ట్‌ఫోన్",
        "సాఫ్ట్‌వేర్",
        "యాప్",
        "యాప్స్",
        "ఇంటర్నెట్",
        "సైబర్ భద్రత",
        "కంప్యూటర్",
        "ల్యాప్‌టాప్",
        "గూగుల్",
        "మైక్రోసాఫ్ట్",
        "ఆపిల్",
        "ఛాట్‌జీపీటీ",
        "చాట్ జీపీటీ",
        "రోబోట్",
        "డిజిటల్",
        "ఉపగ్రహం",
        "టెక్",
        "technology",
        "artificial intelligence",
        "ai",
        "smartphone",
        "mobile phone",
        "software",
        "app",
        "apps",
        "internet",
        "cybersecurity",
        "computer",
        "laptop",
        "google",
        "microsoft",
        "apple",
        "chatgpt",
        "robot",
        "digital",
        "satellite",
        "startup",
        "innovation",
        "space technology",
    ],
}


VALID_CATEGORIES = set(CATEGORY_KEYWORDS) | {"general"}


# ============================================================
# REGION CLASSIFICATION
# ============================================================

def detect_region(title, summary=""):
    """
    Classify the article using geographic keywords.

    Note: keyword matching is not a substitute for understanding
    the article's main geographic focus.
    """
    text = normalize_text(f"{title} {summary}")

    if contains_keyword(text, LOCAL_KEYWORDS):
        return "local"

    if contains_keyword(text, TELANGANA_KEYWORDS):
        return "telangana"

    return "national"


# ============================================================
# CATEGORY CLASSIFICATION
# ============================================================

def get_category(title, summary=""):
    """Return a matching news category or general."""
    text = normalize_text(f"{title} {summary}")

    # Specific news types take priority over broad categories.
    priority = [
        "education_jobs",
        "sports",
        "crime",
        "agriculture",
        "health",
        "politics",
        "entertainment",
        "technology",
    ]

    for category in priority:
        keywords = CATEGORY_KEYWORDS.get(category, [])

        if contains_keyword(text, keywords):
            return category

    return "general"


# ============================================================
# SOURCE NAME
# ============================================================

def get_source_name(url, feed=None):
    """Determine a readable source name."""
    if feed:
        title = normalize_text(
            getattr(feed, "feed", {}).get("title", "")
        )

        if title:
            return title[:200]

    hostname = urlparse(url).hostname or "Unknown source"

    hostname = hostname.lower()
    hostname = hostname.removeprefix("www.")

    return hostname


# ============================================================
# PUBLISHED DATE
# ============================================================

def get_article_date(entry):
    """Extract a publication date from an RSS entry."""
    date_value = (
        entry.get("published")
        or entry.get("updated")
        or entry.get("created")
    )

    if not date_value:
        parsed = (
            entry.get("published_parsed")
            or entry.get("updated_parsed")
        )

        if parsed:
            try:
                from time import mktime

                timestamp = mktime(parsed)

                return datetime.fromtimestamp(
                    timestamp,
                    tz=timezone.utc,
                )

            except (ValueError, OverflowError, OSError):
                return None

        return None

    try:
        parsed_date = parsedate_to_datetime(date_value)

        if parsed_date.tzinfo is None:
            parsed_date = parsed_date.replace(
                tzinfo=timezone.utc
            )

        return parsed_date.astimezone(timezone.utc)

    except (TypeError, ValueError, OverflowError):
        try:
            parsed_date = datetime.fromisoformat(
                date_value.replace("Z", "+00:00")
            )

            if parsed_date.tzinfo is None:
                parsed_date = parsed_date.replace(
                    tzinfo=timezone.utc
                )

            return parsed_date.astimezone(timezone.utc)

        except (TypeError, ValueError, OverflowError):
            return None


def is_recent_article(published_at, max_age_days=None):
    """Return True if an article is within the configured age limit."""
    if published_at is None:
        # Do not silently discard articles without publication dates.
        return True

    max_age_days = (
        MAX_AGE_DAYS
        if max_age_days is None
        else max_age_days
    )

    if max_age_days <= 0:
        return True

    cutoff = datetime.now(timezone.utc) - timedelta(
        days=max_age_days
    )

    return published_at >= cutoff


# ============================================================
# ARTICLE IDENTIFICATION
# ============================================================

def get_article_id(link, title=""):
    """Create a stable ID from the article URL or title."""
    identity = normalize_text(link).lower()

    if not identity:
        identity = normalize_text(title).lower()

    return hashlib.sha256(
        identity.encode("utf-8")
    ).hexdigest()


# ============================================================
# FEED COLLECTION
# ============================================================

def collect_feed(
    feed_url,
    limit_per_feed=DEFAULT_LIMIT_PER_FEED,
    telugu_only=False,
    region=None,
    category=None,
    max_age_days=None,
    seen_ids=None,
):
    """Collect articles from one RSS feed."""
    articles = []
    seen_ids = seen_ids if seen_ids is not None else set()

    added = 0
    skipped = 0

    logger.info("Fetching feed: %s", feed_url)

    try:
        response = requests.get(
            feed_url,
            headers={"User-Agent": USER_AGENT},
            timeout=REQUEST_TIMEOUT,
        )

        response.raise_for_status()

        parsed_feed = feedparser.parse(response.content)

    except requests.RequestException as exc:
        logger.error(
            "Feed request failed for %s: %s",
            feed_url,
            exc,
        )

        return articles

    except Exception:
        logger.exception("Unexpected error reading %s", feed_url)
        return articles

    if not parsed_feed.entries:
        logger.warning("No entries found: %s", feed_url)
        return articles

    source_name = get_source_name(
        feed_url,
        parsed_feed,
    )

    for entry in parsed_feed.entries:
        if added >= limit_per_feed:
            break

        title = normalize_text(entry.get("title", ""))

        if not title:
            skipped += 1
            continue

        link = normalize_text(entry.get("link", ""))

        if not link:
            skipped += 1
            continue

        parsed_link = urlparse(link)

        if parsed_link.scheme not in {"http", "https"}:
            skipped += 1
            continue

        summary = clean_html(
            entry.get("summary", "")
            or entry.get("description", "")
        )

        # Some feeds provide content instead of summary.
        if not summary and entry.get("content"):
            try:
                summary = clean_html(
                    entry["content"][0].get("value", "")
                )
            except (IndexError, AttributeError, TypeError):
                summary = ""

        article_id = get_article_id(link, title)

        if article_id in seen_ids:
            skipped += 1
            continue

        published_at = get_article_date(entry)

        if not is_recent_article(
            published_at,
            max_age_days,
        ):
            skipped += 1
            continue

        # Telugu may appear in either the headline or summary.
        if telugu_only and not (
            is_telugu_text(title)
            or is_telugu_text(summary)
        ):
            skipped += 1
            continue

        detected_region = detect_region(title, summary)
        detected_category = get_category(title, summary)

        if region:
            requested_region = region.strip().lower()

            if requested_region != detected_region:
                skipped += 1
                continue

        if category:
            requested_category = category.strip().lower()

            if requested_category not in VALID_CATEGORIES:
                logger.warning(
                    "Unknown category filter: %s",
                    requested_category,
                )
                skipped += 1
                continue

            if requested_category != detected_category:
                skipped += 1
                continue

        article = {
            "article_id": article_id,
            "title": title,
            "summary": summary,
            "link": link,
            "source_name": source_name,
            "source_feed": feed_url,
            "published_at": published_at,
            "category": detected_category,
            "region": detected_region,
            "language": (
                "te"
                if is_telugu_text(title)
                else "en"
            ),
        }

        articles.append(article)
        seen_ids.add(article_id)
        added += 1

    logger.info(
        "Feed completed: %s | Added: %s | Skipped: %s",
        source_name,
        added,
        skipped,
    )

    return articles


# ============================================================
# COLLECT FROM ALL FEEDS
# ============================================================

def collect_rss_news(
    feeds=None,
    limit_per_feed=DEFAULT_LIMIT_PER_FEED,
    telugu_only=False,
    region=None,
    category=None,
    max_age_days=None,
):
    """
    Collect articles from configured feeds.

    Returns a list of article dictionaries.
    This function does not save articles to the database.
    """
    if feeds is None:
        feeds = configured_feeds()

    if not feeds:
        logger.warning(
            "No RSS feeds configured. Check RSS_FEEDS in .env."
        )

        return []

    all_articles = []
    seen_ids = set()

    logger.info("Configured RSS feeds: %s", len(feeds))

    for feed_url in feeds:
        articles = collect_feed(
            feed_url=feed_url,
            limit_per_feed=limit_per_feed,
            telugu_only=telugu_only,
            region=region,
            category=category,
            max_age_days=max_age_days,
            seen_ids=seen_ids,
        )

        all_articles.extend(articles)

    all_articles.sort(
        key=lambda article: (
            article["published_at"]
            or datetime.min.replace(tzinfo=timezone.utc)
        ),
        reverse=True,
    )

    logger.info(
        "Total unique articles collected: %s",
        len(all_articles),
    )

    return all_articles


# ============================================================
# TERMINAL OUTPUT
# ============================================================

def print_articles(articles):
    """Print collected articles in a readable format."""
    if not articles:
        print("\nNo articles matched your filters.")
        return

    print("\n" + "=" * 80)
    print("VSTV6 DIGITAL MEDIA — RSS NEWS")
    print("=" * 80)

    print(f"\nTotal articles: {len(articles)}")

    for index, article in enumerate(articles, start=1):
        published_at = article.get("published_at")

        if published_at:
            date_text = published_at.strftime(
                "%d-%m-%Y %H:%M UTC"
            )
        else:
            date_text = "Date unavailable"

        print("\n" + "-" * 80)
        print(f"Article: {index}")
        print(f"Title: {article['title']}")
        print(f"Category: {article['category']}")
        print(f"Region: {article['region']}")
        print(f"Language: {article['language']}")
        print(f"Source: {article['source_name']}")
        print(f"Published: {date_text}")

        if article.get("summary"):
            print(f"Summary: {article['summary'][:500]}")

        print(f"Link: {article['link']}")

    print("\n" + "=" * 80)
    print("RSS COLLECTION FINISHED")
    print("=" * 80)


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    try:
        feeds = configured_feeds()

        if not feeds:
            print(
                "ERROR: No RSS feeds configured. "
                "Set RSS_FEEDS in your .env file."
            )

        else:
            articles = collect_rss_news(
                feeds=feeds,
                limit_per_feed=DEFAULT_LIMIT_PER_FEED,
                telugu_only=False,
                max_age_days=MAX_AGE_DAYS,
            )

            print_articles(articles)

    except KeyboardInterrupt:
        print("\nRSS collection interrupted by user.")

    except Exception:
        logger.exception("RSS collector failed.")