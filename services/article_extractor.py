"""Extract readable text from a publicly accessible news article page.

This helper is for editorial review of RSS-imported drafts. It does not
publish articles and does not attempt to bypass paywalls, logins, or access
controls. If extraction fails, the caller should fall back to the RSS summary.
"""

from __future__ import annotations

import logging
from urllib.parse import urlparse

import requests
import trafilatura

logger = logging.getLogger(__name__)

USER_AGENT = "VSTV6NewsCollector/1.0 (editorial review)"
REQUEST_TIMEOUT = 15
MAX_DOWNLOAD_BYTES = 3 * 1024 * 1024
MIN_ARTICLE_CHARACTERS = 200


def extract_article_text(url: str | None) -> str | None:
    """Return extracted article text, or ``None`` when extraction fails.

    Only HTTP/HTTPS URLs are accepted. The response must be HTML and stay
    within ``MAX_DOWNLOAD_BYTES``. This function does not bypass access
    controls. Respect the publisher's terms and reuse permissions.
    """
    if not url:
        return None

    try:
        parsed = urlparse(url)
    except (TypeError, ValueError):
        return None

    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return None

    try:
        with requests.get(
            url,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "text/html,application/xhtml+xml",
            },
            timeout=REQUEST_TIMEOUT,
            stream=True,
            allow_redirects=True,
        ) as response:
            response.raise_for_status()

            content_type = response.headers.get("Content-Type", "").lower()
            if "text/html" not in content_type and "application/xhtml+xml" not in content_type:
                logger.info("Article page is not HTML; skipping extraction: %s", url)
                return None

            chunks: list[bytes] = []
            total_bytes = 0

            for chunk in response.iter_content(chunk_size=16 * 1024):
                if not chunk:
                    continue

                total_bytes += len(chunk)
                if total_bytes > MAX_DOWNLOAD_BYTES:
                    logger.info("Article page exceeds size limit; skipping: %s", url)
                    return None

                chunks.append(chunk)

            raw_html = b"".join(chunks)

            # Use the declared encoding when available, otherwise let UTF-8
            # decode with replacement for malformed characters.
            encoding = response.encoding or "utf-8"
            html = raw_html.decode(encoding, errors="replace")

        extracted = trafilatura.extract(
            html,
            url=url,
            include_comments=False,
            include_tables=True,
            favor_recall=True,
        )

        if not extracted:
            return None

        text = extracted.strip()
        if len(text) < MIN_ARTICLE_CHARACTERS:
            logger.info("Extracted text is too short; using RSS summary: %s", url)
            return None

        return text

    except requests.RequestException as exc:
        logger.info("Could not fetch article page %s: %s", url, exc)
        return None
    except Exception:
        logger.exception("Unexpected article extraction error for %s", url)
        return None
