"""Extract readable text and featured image metadata from news articles."""

from __future__ import annotations

import logging
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

import requests
import trafilatura

logger = logging.getLogger(__name__)

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)

REQUEST_TIMEOUT = 15
MAX_DOWNLOAD_BYTES = 3 * 1024 * 1024
MIN_ARTICLE_CHARACTERS = 200
PERMANENT_HTTP_ERRORS = {404, 410}

IMAGE_METADATA_KEYS = {
    "og:image",
    "og:image:url",
    "og:image:secure_url",
    "twitter:image",
    "twitter:image:src",
    "image",
    "thumbnail",
    "thumbnailurl",
}


class _ArticleMetadataParser(HTMLParser):
    """Extract featured-image URLs from HTML metadata and image elements."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.image_urls: list[str] = []
        self.fallback_images: list[str] = []

    def handle_starttag(self, tag, attrs):
        attributes = {
            str(key).lower(): value
            for key, value in attrs
            if key
        }

        tag = tag.lower()

        if tag == "meta":
            key = (
                attributes.get("property")
                or attributes.get("name")
                or attributes.get("itemprop")
                or ""
            ).strip().lower()

            content = attributes.get("content")

            if key in IMAGE_METADATA_KEYS and content:
                self.image_urls.append(content.strip())

        elif tag == "link":
            rel = (
                attributes.get("rel") or ""
            ).lower().split()

            href = attributes.get("href")

            if href and (
                "image_src" in rel
                or "preload" in rel
                and attributes.get("as") == "image"
            ):
                self.image_urls.append(href.strip())

        elif tag == "img":
            # Prefer larger image variants when available.
            candidates = (
                "data-original",
                "data-lazy-src",
                "data-src",
                "data-original-src",
                "src",
            )

            for attribute in candidates:
                value = attributes.get(attribute)

                if value:
                    self.fallback_images.append(value.strip())

            # Some sites put the real image URL in srcset.
            srcset = attributes.get("srcset") or attributes.get("data-srcset")

            if srcset:
                for item in srcset.split(","):
                    candidate = item.strip().split()

                    if candidate:
                        self.fallback_images.append(candidate[0])

        elif tag == "source":
            srcset = attributes.get("srcset")

            if srcset:
                for item in srcset.split(","):
                    candidate = item.strip().split()

                    if candidate:
                        self.fallback_images.append(candidate[0])


def _is_valid_image_url(url: str | None) -> bool:
    """Accept absolute HTTP/HTTPS URLs without embedded credentials."""
    if not url or not isinstance(url, str):
        return False

    url = url.strip()

    if not url or url.startswith(
        ("data:", "blob:", "javascript:")
    ):
        return False

    try:
        parsed = urlparse(url)
    except (TypeError, ValueError):
        return False

    return (
        parsed.scheme.lower() in {"http", "https"}
        and bool(parsed.hostname)
        and not parsed.username
        and not parsed.password
    )


def _clean_image_url(
    value: str | None,
    page_url: str,
) -> str | None:
    """Resolve relative image URLs and reject obvious placeholders."""
    if not value:
        return None

    value = value.strip()

    if not value:
        return None

    if value.startswith("//"):
        value = "https:" + value

    absolute_url = urljoin(page_url, value)

    if not _is_valid_image_url(absolute_url):
        return None

    parsed = urlparse(absolute_url)
    path = parsed.path.lower()

    if path.endswith(".svg"):
        return None

    if any(
        word in path
        for word in (
            "favicon",
            "placeholder",
            "blank.gif",
            "spacer.gif",
        )
    ):
        return None

    return absolute_url


def _select_image(
    parser: _ArticleMetadataParser,
    page_url: str,
) -> str | None:
    """Choose the first usable metadata image, then an HTML image."""
    candidates = (
        parser.image_urls + parser.fallback_images
    )

    seen = set()

    for candidate in candidates:
        cleaned = _clean_image_url(candidate, page_url)

        if not cleaned or cleaned in seen:
            continue

        seen.add(cleaned)
        return cleaned

    return None


def _validate_article_url(url: str | None) -> bool:
    """Validate article URL before making an HTTP request."""

    if not url or not isinstance(url, str):
        return False

    try:
        parsed = urlparse(url)
    except (TypeError, ValueError):
        return False

    return (
        parsed.scheme.lower() in {"http", "https"}
        and bool(parsed.hostname)
        and not parsed.username
        and not parsed.password
    )


def extract_article_page(
    url: str | None,
) -> tuple[str | None, str | None]:
    """
    Return readable article text and featured-image URL.

    Handles permanent HTTP errors separately.
    One unavailable article will not interrupt RSS processing.

    Returns:
        (article_text, image_url)

        Both values can be None if extraction fails.
        Image URL can still be returned if text extraction fails.
    """
    if not _validate_article_url(url):
        logger.warning(
            "Invalid article URL: %s",
            url,
        )
        return None, None

    try:
        with requests.get(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": (
                    "text/html,application/xhtml+xml,"
                    "application/xml;q=0.9,*/*;q=0.8"
                ),
            },
            timeout=REQUEST_TIMEOUT,
            stream=True,
            allow_redirects=True,
        ) as response:
            if response.status_code in PERMANENT_HTTP_ERRORS:
                logger.info(
                    "Article permanently unavailable "
                    "(HTTP %s): %s",
                    response.status_code,
                    url,
                )
                return None, None

            response.raise_for_status()

            content_type = response.headers.get(
                "Content-Type", ""
            ).lower()

            if (
                "text/html" not in content_type
                and "application/xhtml+xml" not in content_type
            ):
                logger.info(
                    "Article page is not HTML: %s",
                    url,
                )
                return None, None

            chunks: list[bytes] = []
            total_bytes = 0

            for chunk in response.iter_content(
                chunk_size=16 * 1024
            ):
                if not chunk:
                    continue

                total_bytes += len(chunk)

                if total_bytes > MAX_DOWNLOAD_BYTES:
                    logger.warning(
                        "Article page exceeds size limit: %s",
                        url,
                    )
                    return None, None

                chunks.append(chunk)

            raw_html = b"".join(chunks)
            encoding = response.encoding or "utf-8"
            html = raw_html.decode(
                encoding,
                errors="replace",
            )
            page_url = response.url or url

        parser = _ArticleMetadataParser()

        try:
            parser.feed(html)
            parser.close()
        except Exception:
            logger.debug(
                "HTML metadata parsing failed: %s",
                page_url,
                exc_info=True,
            )

        image_url = _select_image(parser, page_url)

        if image_url:
            logger.debug(
                "Featured image found: %s",
                image_url,
            )
        else:
            logger.info(
                "No featured image found: %s",
                page_url,
            )

        extracted = trafilatura.extract(
            html,
            url=page_url,
            include_comments=False,
            include_tables=True,
            favor_recall=True,
        )

        if not extracted:
            logger.info(
                "No readable article text extracted: %s",
                page_url,
            )
            return None, image_url

        text = extracted.strip()

        if len(text) < MIN_ARTICLE_CHARACTERS:
            logger.info(
                "Article text too short (%s characters): %s",
                len(text),
                page_url,
            )
            return None, image_url

        logger.info(
            "Article extraction successful: "
            "%s (%s characters)",
            page_url,
            len(text),
        )

        return text, image_url

    except requests.HTTPError as exc:
        status_code = (
            exc.response.status_code
            if exc.response is not None
            else None
        )

        if status_code in PERMANENT_HTTP_ERRORS:
            logger.info(
                "Article unavailable (HTTP %s): %s",
                status_code,
                url,
            )
        else:
            logger.warning(
                "HTTP error extracting article %s: %s",
                url,
                exc,
            )

        return None, None

    except requests.Timeout:
        logger.warning(
            "Article request timed out: %s",
            url,
        )
        return None, None

    except requests.ConnectionError as exc:
        logger.warning(
            "Article connection failed: %s - %s",
            url,
            exc,
        )
        return None, None

    except requests.RequestException as exc:
        logger.warning(
            "Could not fetch article page %s: %s",
            url,
            exc,
        )
        return None, None

    except Exception:
        logger.exception(
            "Unexpected article extraction error: %s",
            url,
        )
        return None, None


def extract_article_text(
    url: str | None,
) -> str | None:
    """Return extracted article text, or None on failure."""
    text, _ = extract_article_page(url)
    return text