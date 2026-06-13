from datetime import UTC, datetime

import httpx
import respx

from fbpost_to_wordpress.facebook import FacebookScraper, image_extension_from_url


@respx.mock
def test_facebook_scraper_discovers_posts_from_apify() -> None:
    route = respx.post("https://api.apify.com/v2/acts/apify~facebook-posts-scraper/run-sync-get-dataset-items").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "postId": "123",
                    "url": "https://www.facebook.com/page/posts/123",
                    "time": "2026-01-20T13:00:05.000Z",
                    "text": "isi post",
                }
            ],
        )
    )

    scraper = FacebookScraper(token="apify-token")
    posts = scraper.discover_posts("https://www.facebook.com/page", count=1, skip=0)

    assert route.called
    assert posts[0].post_id == "123"
    assert posts[0].post_url.endswith("/123")
    assert posts[0].published_at == datetime(2026, 1, 20, 13, 0, 5, tzinfo=UTC)


@respx.mock
def test_facebook_scraper_scrapes_text_and_images_from_apify() -> None:
    respx.post("https://api.apify.com/v2/acts/apify~facebook-posts-scraper/run-sync-get-dataset-items").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "postId": "123",
                    "url": "https://www.facebook.com/page/posts/123",
                    "time": "2026-01-20T13:00:05.000Z",
                    "text": "isi post",
                    "images": [
                        {"url": "https://cdn.example.com/image-1.jpg"},
                        {"src": "https://cdn.example.com/image-2.png"},
                    ],
                }
            ],
        )
    )

    scraper = FacebookScraper(token="apify-token")
    discovered = scraper.discover_posts("https://www.facebook.com/page", count=1, skip=0)[0]
    scraped = scraper.scrape_post(discovered)

    assert scraped.content == "isi post"
    assert scraped.images == [
        "https://cdn.example.com/image-1.jpg",
        "https://cdn.example.com/image-2.png",
    ]


@respx.mock
def test_facebook_scraper_extracts_images_from_media_field() -> None:
    respx.post("https://api.apify.com/v2/acts/apify~facebook-posts-scraper/run-sync-get-dataset-items").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "postId": "123",
                    "url": "https://www.facebook.com/page/posts/123",
                    "time": "2026-01-20T13:00:05.000Z",
                    "text": "isi post",
                    "media": [
                        {"url": "https://www.facebook.com/page/posts/123"},
                        {
                            "thumbnail": "https://cdn.example.com/thumb.jpg",
                            "image": {"uri": "https://cdn.example.com/full.jpg"},
                        },
                    ],
                }
            ],
        )
    )

    scraper = FacebookScraper(token="apify-token")
    discovered = scraper.discover_posts("https://www.facebook.com/page", count=1, skip=0)[0]
    scraped = scraper.scrape_post(discovered)

    assert scraped.images == ["https://cdn.example.com/full.jpg"]


@respx.mock
def test_facebook_scraper_prefers_largest_image_variant_per_media_object() -> None:
    respx.post("https://api.apify.com/v2/acts/apify~facebook-posts-scraper/run-sync-get-dataset-items").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "postId": "123",
                    "url": "https://www.facebook.com/page/posts/123",
                    "time": "2026-01-20T13:00:05.000Z",
                    "text": "isi post",
                    "media": [
                        {
                            "src": "https://cdn.example.com/small.jpg",
                            "width": 300,
                            "height": 200,
                            "image": {
                                "uri": "https://cdn.example.com/large.jpg",
                                "width": 1600,
                                "height": 1200,
                            },
                            "thumbnail": "https://cdn.example.com/thumb.jpg",
                        }
                    ],
                }
            ],
        )
    )

    scraper = FacebookScraper(token="apify-token")
    discovered = scraper.discover_posts("https://www.facebook.com/page", count=1, skip=0)[0]
    scraped = scraper.scrape_post(discovered)

    assert scraped.images == ["https://cdn.example.com/large.jpg"]


def test_image_extension_from_url_normalizes_suffix() -> None:
    assert image_extension_from_url("https://cdn.example.com/photo.png?x=1") == "png"
    assert image_extension_from_url("https://cdn.example.com/photo") == "jpg"


@respx.mock
def test_facebook_scraper_discover_posts_returns_partial_results_without_error() -> None:
    respx.post("https://api.apify.com/v2/acts/apify~facebook-posts-scraper/run-sync-get-dataset-items").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "postId": "123",
                    "url": "https://www.facebook.com/page/posts/123",
                    "time": "2026-01-20T13:00:05.000Z",
                    "text": "isi post",
                }
            ],
        )
    )

    scraper = FacebookScraper(token="apify-token")
    posts = scraper.discover_posts("https://www.facebook.com/page", count=2, skip=0)

    assert [post.post_id for post in posts] == ["123"]


@respx.mock
def test_facebook_scraper_discover_posts_returns_empty_when_skip_exceeds_items() -> None:
    respx.post("https://api.apify.com/v2/acts/apify~facebook-posts-scraper/run-sync-get-dataset-items").mock(
        return_value=httpx.Response(
            200,
            json=[
                {
                    "postId": "123",
                    "url": "https://www.facebook.com/page/posts/123",
                    "time": "2026-01-20T13:00:05.000Z",
                    "text": "isi post",
                }
            ],
        )
    )

    scraper = FacebookScraper(token="apify-token")
    posts = scraper.discover_posts("https://www.facebook.com/page", count=1, skip=2)

    assert posts == []
