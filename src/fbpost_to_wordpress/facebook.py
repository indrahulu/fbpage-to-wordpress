from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from urllib.parse import urlparse

import httpx

from fbpost_to_wordpress.models import DiscoveredPost, ScrapedPost


@dataclass(slots=True)
class ApifyRunConfig:
    token: str
    actor_id: str = "apify/facebook-posts-scraper"
    base_url: str = "https://api.apify.com/v2"


class FacebookScraper:
    def __init__(self, token: str, actor_id: str = "apify/facebook-posts-scraper") -> None:
        self.run_config = ApifyRunConfig(token=token, actor_id=actor_id)

    def discover_posts(self, page_url: str, count: int, skip: int) -> list[DiscoveredPost]:
        items = self._fetch_posts(page_url=page_url, results_limit=count + skip)
        if len(items) < count + skip:
            raise RuntimeError(f"Only discovered {len(items)} posts, but need {count + skip} for skip={skip}, count={count}.")
        return [self._to_discovered_post(page_url, item) for item in items[skip : skip + count]]

    def scrape_post(self, discovered: DiscoveredPost) -> ScrapedPost:
        items = self._fetch_posts(page_url=discovered.page_url, results_limit=30)
        match = next((item for item in items if str(item.get("postId")) == discovered.post_id), None)
        if match is None:
            raise RuntimeError(f"Apify did not return details for Facebook post {discovered.post_id}.")
        return ScrapedPost(
            post_id=discovered.post_id,
            post_url=self._pick_post_url(match, fallback=discovered.post_url),
            page_url=discovered.page_url,
            content=self._pick_text(match),
            published_at=self._pick_datetime(match) or discovered.published_at,
            images=self._extract_image_urls(match),
        )

    def download_image(self, image_url: str) -> bytes:
        with httpx.Client(follow_redirects=True, timeout=60) as client:
            response = client.get(image_url, headers={"User-Agent": "Mozilla/5.0"})
            response.raise_for_status()
            return response.content

    def _fetch_posts(self, page_url: str, results_limit: int) -> list[dict]:
        actor_path = self.run_config.actor_id.replace("/", "~")
        endpoint = f"{self.run_config.base_url}/acts/{actor_path}/run-sync-get-dataset-items"
        payload = {
            "startUrls": [{"url": page_url}],
            "resultsLimit": results_limit,
        }
        params = {
            "token": self.run_config.token,
            "format": "json",
            "clean": "true",
        }
        with httpx.Client(timeout=180) as client:
            response = client.post(endpoint, params=params, json=payload)
            response.raise_for_status()
            data = response.json()
        if not isinstance(data, list):
            raise RuntimeError("Unexpected Apify response format.")
        return data

    def _to_discovered_post(self, page_url: str, item: dict) -> DiscoveredPost:
        post_id = str(item.get("postId") or item.get("facebookId") or "").strip()
        if not post_id:
            raise RuntimeError("Apify item is missing postId.")
        return DiscoveredPost(
            post_id=post_id,
            post_url=self._pick_post_url(item, fallback=page_url),
            page_url=page_url,
            published_at=self._pick_datetime(item),
        )

    def _pick_post_url(self, item: dict, fallback: str) -> str:
        return str(item.get("url") or item.get("postUrl") or fallback)

    def _pick_text(self, item: dict) -> str:
        text = item.get("text") or item.get("caption") or item.get("content") or ""
        if not isinstance(text, str) or not text.strip():
            raise RuntimeError("Apify item is missing post text.")
        return text.strip()

    def _pick_datetime(self, item: dict) -> datetime | None:
        value = item.get("time") or item.get("publishedAt")
        if isinstance(value, str) and value:
            return datetime.fromisoformat(value.replace("Z", "+00:00"))
        timestamp = item.get("timestamp")
        if isinstance(timestamp, (int, float)):
            return datetime.fromtimestamp(timestamp, tz=UTC)
        return None

    def _extract_image_urls(self, item: dict) -> list[str]:
        seen: list[str] = []

        def add(url: str | None) -> None:
            if isinstance(url, str) and url.startswith("http") and url not in seen:
                seen.append(url)

        def add_best_from_mapping(mapping: dict, include_plain_url: bool = True) -> None:
            candidates: list[tuple[int, str]] = []

            def add_candidate(url: str | None, width: int | None = None, height: int | None = None) -> None:
                if not isinstance(url, str) or not url.startswith("http"):
                    return
                area = 0
                if isinstance(width, int) and isinstance(height, int) and width > 0 and height > 0:
                    area = width * height
                candidates.append((area, url))

            image = mapping.get("image")
            if isinstance(image, dict):
                add_candidate(image.get("uri"), image.get("width"), image.get("height"))

            if include_plain_url:
                add_candidate(mapping.get("url"), mapping.get("width"), mapping.get("height"))
            add_candidate(mapping.get("src"), mapping.get("width"), mapping.get("height"))
            add_candidate(mapping.get("imageUrl"), mapping.get("width"), mapping.get("height"))
            add_candidate(mapping.get("thumbnailUrl"), mapping.get("width"), mapping.get("height"))
            add_candidate(mapping.get("thumbnail"), mapping.get("width"), mapping.get("height"))

            if candidates:
                candidates.sort(key=lambda item: item[0], reverse=True)
                add(candidates[0][1])

        for key in ("image", "imageUrl", "thumbnail", "thumbnailUrl"):
            add(item.get(key))

        for list_key in ("images", "imageUrls", "mediaUrls", "photos"):
            values = item.get(list_key)
            if isinstance(values, list):
                for value in values:
                    if isinstance(value, str):
                        add(value)
                    elif isinstance(value, dict):
                        add_best_from_mapping(value, include_plain_url=True)

        attachments = item.get("attachments")
        if isinstance(attachments, list):
            for attachment in attachments:
                if isinstance(attachment, dict):
                    add_best_from_mapping(attachment, include_plain_url=True)

        media = item.get("media")
        if isinstance(media, list):
            for media_item in media:
                if isinstance(media_item, dict):
                    add_best_from_mapping(media_item, include_plain_url=False)
        return seen


def image_extension_from_url(image_url: str) -> str:
    path = urlparse(image_url).path
    suffix = Path(path).suffix.lower().strip(".")
    return suffix if suffix in {"jpg", "jpeg", "png", "webp", "gif"} else "jpg"
