from __future__ import annotations

import re
from datetime import UTC, datetime

from slugify import slugify

from fbpost_to_wordpress.models import RedactedContent


def ensure_utc(dt: datetime | None) -> datetime | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def build_post_folder_name(published_at: datetime | None, post_id: str) -> str:
    effective = ensure_utc(published_at) or datetime.now(tz=UTC)
    return f"{effective:%Y-%m-%d}-{slugify(post_id, separator='-', lowercase=True)}"


def parse_redacted_markdown(markdown: str) -> RedactedContent:
    normalized = markdown.strip()
    match = re.match(r"^#\s+(.+?)\n+(.+)$", normalized, flags=re.DOTALL)
    if not match:
        raise ValueError("content-redacted.md must start with '# Title' followed by body text.")
    title = match.group(1).strip()
    body = match.group(2).strip()
    if not title or not body:
        raise ValueError("Redacted content must contain non-empty title and body.")
    return RedactedContent(title=title, body=body, raw_markdown=normalized + "\n")


def extract_post_id_from_url(url: str) -> str | None:
    patterns = [
        r"story_fbid=(\d+)",
        r"fbid=(\d+)",
        r"/posts/(\d+)",
        r"/videos/(\d+)",
        r"/permalink/(\d+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None

