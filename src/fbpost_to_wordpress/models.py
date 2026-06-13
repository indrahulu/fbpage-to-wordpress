from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from pathlib import Path


class Stage(StrEnum):
    DISCOVERED = "discovered"
    SCRAPED = "scraped"
    REDACTED = "redacted"
    PUBLISHED = "published"
    FAILED = "failed"


@dataclass(slots=True)
class DiscoveredPost:
    post_id: str
    post_url: str
    page_url: str
    published_at: datetime | None = None


@dataclass(slots=True)
class ScrapedPost:
    post_id: str
    post_url: str
    page_url: str
    content: str
    published_at: datetime | None
    images: list[str] = field(default_factory=list)


@dataclass(slots=True)
class RedactedContent:
    title: str
    body: str
    raw_markdown: str


@dataclass(slots=True)
class FeaturedImageSelection:
    selected_image: str
    reason: str


@dataclass(slots=True)
class WordPressMedia:
    id: int
    source_url: str


@dataclass(slots=True)
class WordPressPostRef:
    id: int
    status: str


@dataclass(slots=True)
class PostRecord:
    post_id: str
    post_url: str
    page_url: str
    folder: Path
    published_at: datetime | None = None
