from datetime import UTC, datetime
from pathlib import Path

import httpx
import respx

from fbpost_to_wordpress.models import RedactedContent, WordPressMedia
from fbpost_to_wordpress.wordpress import WordPressClient


@respx.mock
def test_wordpress_upload_media_posts_binary_file(workdir: Path) -> None:
    image_path = workdir / "photo.jpg"
    image_path.write_bytes(b"image-data")
    route = respx.post("https://example.com/wp-json/wp/v2/media").mock(
        return_value=httpx.Response(201, json={"id": 77, "source_url": "https://example.com/uploads/photo.jpg"})
    )

    client = WordPressClient("https://example.com", "admin", "secret")
    media_id = client.upload_media(image_path)

    assert media_id.id == 77
    assert media_id.source_url == "https://example.com/uploads/photo.jpg"
    assert route.called
    request = route.calls[0].request
    assert request.headers["Authorization"].startswith("Basic ")
    assert request.headers["Content-Type"] == "image/jpeg"
    assert request.content == b"image-data"


@respx.mock
def test_wordpress_normalizes_application_password_spaces(workdir: Path) -> None:
    image_path = workdir / "photo.jpg"
    image_path.write_bytes(b"image-data")
    route = respx.post("https://example.com/wp-json/wp/v2/media").mock(
        return_value=httpx.Response(201, json={"id": 77, "source_url": "https://example.com/uploads/photo.jpg"})
    )

    client = WordPressClient("https://example.com", "admin", "ab cd ef gh")
    client.upload_media(image_path)

    request = route.calls[0].request
    assert request.headers["Authorization"] == "Basic YWRtaW46YWJjZGVmZ2g="


@respx.mock
def test_wordpress_create_post_sends_title_body_and_featured_media() -> None:
    respx.get("https://example.com/wp-json/wp/v2/categories").mock(
        return_value=httpx.Response(200, json=[{"id": 12, "name": "Berita", "slug": "berita"}])
    )
    route = respx.post("https://example.com/wp-json/wp/v2/posts").mock(
        return_value=httpx.Response(201, json={"id": 321})
    )
    client = WordPressClient("https://example.com", "admin", "secret")

    post_id = client.create_post(
        RedactedContent(title="Judul", body="Paragraf satu\n\nParagraf dua", raw_markdown="# Judul\n\nParagraf"),
        media_items=[
            WordPressMedia(id=88, source_url="https://example.com/uploads/image-1.jpg"),
            WordPressMedia(id=99, source_url="https://example.com/uploads/image-2.jpg"),
        ],
        source_post_id="123",
        source_post_url="https://facebook.com/posts/123",
        published_at=datetime(2026, 6, 9, 4, 30, tzinfo=UTC),
    )

    assert post_id == 321
    payload = route.calls[0].request.read().decode("utf-8")
    assert '"title":"Judul"' in payload
    assert '"status":"draft"' in payload
    assert '"featured_media":88' in payload
    assert '"categories":[12]' in payload
    assert '"date":"2026-06-09T11:30:00+07:00"' in payload
    assert '"date_gmt":"2026-06-09T04:30:00"' in payload
    assert 'fbpost-to-wordpress:{\\"source_post_id\\":\\"123\\",\\"source_post_url\\":\\"https://facebook.com/posts/123\\"}' in payload
    assert "wp:gallery" in payload
    assert 'src=\\"https://example.com/uploads/image-1.jpg\\"' in payload
    assert 'src=\\"https://example.com/uploads/image-2.jpg\\"' in payload


@respx.mock
def test_wordpress_create_post_creates_berita_category_when_missing() -> None:
    respx.get("https://example.com/wp-json/wp/v2/categories").mock(return_value=httpx.Response(200, json=[]))
    create_category = respx.post("https://example.com/wp-json/wp/v2/categories").mock(
        return_value=httpx.Response(201, json={"id": 44, "name": "Berita", "slug": "berita"})
    )
    create_post = respx.post("https://example.com/wp-json/wp/v2/posts").mock(
        return_value=httpx.Response(201, json={"id": 987})
    )

    client = WordPressClient("https://example.com", "admin", "secret")
    post_id = client.create_post(
        RedactedContent(title="Judul", body="Isi", raw_markdown="# Judul\n\nIsi"),
        media_items=[],
        source_post_id="123",
        source_post_url="https://facebook.com/posts/123",
    )

    assert post_id == 987
    assert create_category.called
    assert '"categories":[44]' in create_post.calls[0].request.read().decode("utf-8")


@respx.mock
def test_wordpress_find_post_by_source_id_matches_only_marker_posts() -> None:
    respx.get("https://example.com/wp-json/wp/v2/posts").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "id": 10,
                    "status": "draft",
                    "content": {"raw": "<p>tanpa marker</p>"},
                },
                {
                    "id": 11,
                    "status": "publish",
                    "content": {
                        "raw": '<!-- fbpost-to-wordpress:{"source_post_id":"abc","source_post_url":"https://facebook.com/posts/abc"} -->\n<p>isi</p>'
                    },
                },
            ],
        )
    )
    client = WordPressClient("https://example.com", "admin", "secret")
    result = client.find_post_by_source_id("abc")
    assert result is not None
    assert result.id == 11
    assert result.status == "publish"


@respx.mock
def test_wordpress_update_post_uses_existing_post_endpoint() -> None:
    respx.get("https://example.com/wp-json/wp/v2/categories").mock(
        return_value=httpx.Response(200, json=[{"id": 12, "name": "Berita", "slug": "berita"}])
    )
    route = respx.post("https://example.com/wp-json/wp/v2/posts/321").mock(
        return_value=httpx.Response(200, json={"id": 321})
    )
    client = WordPressClient("https://example.com", "admin", "secret")
    post_id = client.update_post(
        321,
        RedactedContent(title="Judul", body="Isi", raw_markdown="# Judul\n\nIsi"),
        media_items=[WordPressMedia(id=88, source_url="https://example.com/uploads/image-1.jpg")],
        source_post_id="123",
        source_post_url="https://facebook.com/posts/123",
    )
    assert post_id == 321
    assert route.called
