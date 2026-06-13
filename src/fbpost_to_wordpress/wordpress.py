from __future__ import annotations

import base64
import json
import mimetypes
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from fbpost_to_wordpress.models import RedactedContent, WordPressMedia, WordPressPostRef
from fbpost_to_wordpress.utils import ensure_utc


JAKARTA_TZ = timezone(timedelta(hours=7), name="Asia/Jakarta")


class WordPressClient:
    def __init__(self, base_url: str, username: str, app_password: str) -> None:
        self.base_url = base_url.rstrip("/")
        normalized_username = username.strip()
        normalized_password = "".join(app_password.split())
        token = base64.b64encode(f"{normalized_username}:{normalized_password}".encode("utf-8")).decode("ascii")
        self.headers = {"Authorization": f"Basic {token}"}

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8), reraise=True)
    def upload_media(self, image_path: Path) -> WordPressMedia:
        media_url = f"{self.base_url}/wp-json/wp/v2/media"
        mime_type = mimetypes.guess_type(image_path.name)[0] or "application/octet-stream"
        headers = {
            **self.headers,
            "Content-Disposition": f'attachment; filename="{image_path.name}"',
            "Content-Type": mime_type,
        }
        with httpx.Client(timeout=90) as client:
            response = client.post(media_url, headers=headers, content=image_path.read_bytes())
            response.raise_for_status()
            payload = response.json()
            return WordPressMedia(id=int(payload["id"]), source_url=str(payload["source_url"]))

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8), reraise=True)
    def create_post(
        self,
        content: RedactedContent,
        media_items: list[WordPressMedia],
        source_post_id: str,
        source_post_url: str,
        published_at: datetime | None = None,
        featured_media_id: int | None = None,
    ) -> int:
        post_url = f"{self.base_url}/wp-json/wp/v2/posts"
        payload = {
            "title": content.title,
            "content": self._build_html_content(content.body, media_items, source_post_id, source_post_url),
            "status": "draft",
            "categories": [self._ensure_category("Berita")],
        }
        if published_at is not None:
            date_local = self._to_jakarta_datetime(published_at)
            payload["date"] = date_local.isoformat()
            payload["date_gmt"] = ensure_utc(date_local).replace(tzinfo=None).isoformat()
        if featured_media_id is not None:
            payload["featured_media"] = featured_media_id
        elif media_items:
            payload["featured_media"] = media_items[0].id
        with httpx.Client(timeout=90) as client:
            response = client.post(post_url, headers={**self.headers, "Content-Type": "application/json"}, json=payload)
            response.raise_for_status()
            return int(response.json()["id"])

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8), reraise=True)
    def update_post(
        self,
        post_id: int,
        content: RedactedContent,
        media_items: list[WordPressMedia],
        source_post_id: str,
        source_post_url: str,
        published_at: datetime | None = None,
        featured_media_id: int | None = None,
    ) -> int:
        post_url = f"{self.base_url}/wp-json/wp/v2/posts/{post_id}"
        payload = {
            "title": content.title,
            "content": self._build_html_content(content.body, media_items, source_post_id, source_post_url),
            "status": "draft",
            "categories": [self._ensure_category("Berita")],
        }
        if published_at is not None:
            date_local = self._to_jakarta_datetime(published_at)
            payload["date"] = date_local.isoformat()
            payload["date_gmt"] = ensure_utc(date_local).replace(tzinfo=None).isoformat()
        if featured_media_id is not None:
            payload["featured_media"] = featured_media_id
        elif media_items:
            payload["featured_media"] = media_items[0].id
        with httpx.Client(timeout=90) as client:
            response = client.post(post_url, headers={**self.headers, "Content-Type": "application/json"}, json=payload)
            response.raise_for_status()
            return int(response.json()["id"])

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8), reraise=True)
    def find_post_by_source_id(self, source_post_id: str) -> WordPressPostRef | None:
        with httpx.Client(timeout=90) as client:
            for status in ("draft", "publish"):
                page = 1
                while True:
                    response = client.get(
                        f"{self.base_url}/wp-json/wp/v2/posts",
                        headers=self.headers,
                        params={
                            "context": "edit",
                            "status": status,
                            "per_page": 100,
                            "page": page,
                        },
                    )
                    response.raise_for_status()
                    items = response.json()
                    if not items:
                        break
                    for item in items:
                        raw_content = str(item.get("content", {}).get("raw", ""))
                        marker = self._extract_source_marker(raw_content)
                        if marker and marker.get("source_post_id") == source_post_id:
                            return WordPressPostRef(id=int(item["id"]), status=str(item["status"]))
                    if len(items) < 100:
                        break
                    page += 1
        return None

    def _ensure_category(self, name: str) -> int:
        categories_url = f"{self.base_url}/wp-json/wp/v2/categories"
        slug = name.strip().lower().replace(" ", "-")
        with httpx.Client(timeout=90) as client:
            response = client.get(categories_url, headers=self.headers, params={"slug": slug})
            response.raise_for_status()
            items = response.json()
            if items:
                return int(items[0]["id"])

            create_response = client.post(
                categories_url,
                headers={**self.headers, "Content-Type": "application/json"},
                json={"name": name, "slug": slug},
            )
            create_response.raise_for_status()
            return int(create_response.json()["id"])

    def _build_html_content(
        self,
        body_markdown: str,
        media_items: list[WordPressMedia],
        source_post_id: str,
        source_post_url: str,
    ) -> str:
        lines = [self._build_source_marker(source_post_id, source_post_url)]
        lines.extend(f"<p>{line}</p>" for line in body_markdown.splitlines() if line.strip())
        if media_items:
            gallery_parts = ['<!-- wp:gallery {"randomOrder":true,"linkTo":"lightbox"} -->']
            gallery_parts.append('<figure class="wp-block-gallery has-nested-images columns-default is-cropped">')
            for media in media_items:
                gallery_parts.extend(
                    [
                        f'<!-- wp:image {{"lightbox":{{"enabled":true}},"id":{media.id},"sizeSlug":"large","linkDestination":"none"}} -->',
                        (
                            f'<figure class="wp-block-image size-large">'
                            f'<img src="{media.source_url}" alt="" class="wp-image-{media.id}"/>'
                            f"</figure>"
                        ),
                        "<!-- /wp:image -->",
                        "",
                    ]
                )
            gallery_parts.append("</figure>")
            gallery_parts.append("<!-- /wp:gallery -->")
            lines.append("\n".join(gallery_parts).strip())
        return "\n".join(lines)

    def _to_jakarta_datetime(self, published_at: datetime) -> datetime:
        if published_at.tzinfo is None:
            return published_at.replace(tzinfo=JAKARTA_TZ)
        return published_at.astimezone(JAKARTA_TZ)

    def _build_source_marker(self, source_post_id: str, source_post_url: str) -> str:
        payload = {
            "source_post_id": source_post_id,
            "source_post_url": source_post_url,
        }
        return f"<!-- fbpost-to-wordpress:{json.dumps(payload, separators=(',', ':'))} -->"

    def _extract_source_marker(self, raw_content: str) -> dict[str, str] | None:
        prefix = "<!-- fbpost-to-wordpress:"
        suffix = " -->"
        start = raw_content.find(prefix)
        if start == -1:
            return None
        end = raw_content.find(suffix, start)
        if end == -1:
            return None
        payload = raw_content[start + len(prefix) : end].strip()
        if not payload:
            return None
        try:
            data = json.loads(payload)
        except json.JSONDecodeError:
            return None
        if not isinstance(data, dict):
            return None
        return data
