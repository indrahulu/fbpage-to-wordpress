import json
from datetime import UTC, datetime
from pathlib import Path

from fbpost_to_wordpress.models import DiscoveredPost, RedactedContent, Stage, WordPressMedia, WordPressPostRef
from fbpost_to_wordpress.pipeline import PostPipeline
from fbpost_to_wordpress.storage import PostStorage


class FakeScraper:
    def discover_posts(self, page_url: str, count: int, skip: int):
        return [
            DiscoveredPost(
                post_id="123",
                post_url="https://facebook.com/posts/123",
                page_url=page_url,
                published_at=datetime(2024, 5, 6, 7, 8, tzinfo=UTC),
            )
        ]

    def scrape_post(self, discovered: DiscoveredPost):
        from fbpost_to_wordpress.models import ScrapedPost

        return ScrapedPost(
            post_id=discovered.post_id,
            post_url=discovered.post_url,
            page_url=discovered.page_url,
            content="konten asli",
            published_at=discovered.published_at,
            images=["https://example.com/image.jpg"],
        )

    def download_image(self, image_url: str) -> bytes:
        return b"image-bytes"


class FakeOpenRouter:
    def __init__(self) -> None:
        self.featured_image_calls = 0

    def redact(self, content: str) -> RedactedContent:
        return RedactedContent(title="Judul", body="Isi", raw_markdown="# Judul\n\nIsi\n")

    def select_featured_image(self, content: str, image_paths: list[Path]):
        from fbpost_to_wordpress.models import FeaturedImageSelection

        self.featured_image_calls += 1
        return FeaturedImageSelection(selected_image=image_paths[-1].name, reason="Paling bagus")


class FakeWordPress:
    def __init__(self) -> None:
        self.uploaded = []
        self.post_creates = 0
        self.post_updates = 0
        self.published_at_values = []
        self.featured_media_ids = []
        self.find_result = None
        self.created_source_ids = []
        self.updated_source_ids = []

    def upload_media(self, image_path: Path) -> int:
        self.uploaded.append(image_path.name)
        media_id = 99 if image_path.name.endswith("1.jpg") else 100
        return WordPressMedia(id=media_id, source_url=f"https://example.com/uploads/{image_path.name}")

    def find_post_by_source_id(self, source_post_id: str):
        return self.find_result

    def create_post(
        self,
        content: RedactedContent,
        media_items: list[WordPressMedia],
        source_post_id: str,
        source_post_url: str,
        published_at=None,
        featured_media_id=None,
    ) -> int:
        self.post_creates += 1
        self.created_source_ids.append(source_post_id)
        self.published_at_values.append(published_at)
        self.featured_media_ids.append(featured_media_id)
        assert content.title == "Judul"
        assert media_items
        return 321

    def update_post(
        self,
        post_id: int,
        content: RedactedContent,
        media_items: list[WordPressMedia],
        source_post_id: str,
        source_post_url: str,
        published_at=None,
        featured_media_id=None,
    ) -> int:
        self.post_updates += 1
        self.updated_source_ids.append(source_post_id)
        self.published_at_values.append(published_at)
        self.featured_media_ids.append(featured_media_id)
        assert post_id == 555
        assert content.title == "Judul"
        assert media_items
        return post_id


def test_pipeline_runs_to_published(workdir: Path) -> None:
    storage = PostStorage(workdir)
    wordpress = FakeWordPress()
    openrouter = FakeOpenRouter()
    pipeline = PostPipeline(storage, FakeScraper(), openrouter, wordpress)
    pipeline.run("https://facebook.com/page", count=1, skip=0, dry_run=False)
    folder = next(workdir.iterdir())
    status = json.loads((folder / "status.json").read_text(encoding="utf-8"))
    assert status["stage"] == "published"
    assert status["wordpress_post_id"] == 321
    assert (folder / "content.md").exists()
    assert (folder / "content-redacted.md").exists()
    assert openrouter.featured_image_calls == 0
    assert wordpress.published_at_values == [datetime(2024, 5, 6, 7, 8, tzinfo=UTC)]
    assert wordpress.featured_media_ids == [99]


def test_pipeline_dry_run_skips_publish(workdir: Path) -> None:
    storage = PostStorage(workdir)
    pipeline = PostPipeline(storage, FakeScraper(), FakeOpenRouter(), FakeWordPress())
    pipeline.run("https://facebook.com/page", count=1, skip=0, dry_run=True)
    folder = next(workdir.iterdir())
    status = json.loads((folder / "status.json").read_text(encoding="utf-8"))
    assert status["stage"] == "redacted"
    assert status["dry_run"] is True
    assert (folder / "publish-preview.md").exists()


def test_pipeline_resume_from_redacted_only_runs_publish(workdir: Path) -> None:
    storage = PostStorage(workdir)
    discovered = FakeScraper().discover_posts("https://facebook.com/page", 1, 0)[0]
    record = storage.build_record(discovered)
    storage.initialize(record, dry_run=False)
    (record.folder / "content.md").write_text("konten asli\n", encoding="utf-8")
    (record.folder / "content-redacted.md").write_text("# Judul\n\nIsi\n", encoding="utf-8")
    (record.folder / "images" / "image-1.jpg").write_bytes(b"image-bytes")
    storage.write_status(record.folder, stage=Stage.FAILED, dry_run=False, last_error="publish failed")

    wordpress = FakeWordPress()
    openrouter = FakeOpenRouter()
    pipeline = PostPipeline(storage, FakeScraper(), openrouter, wordpress)
    pipeline.process_post(discovered, dry_run=False)

    status = json.loads((record.folder / "status.json").read_text(encoding="utf-8"))
    assert status["stage"] == "published"
    assert wordpress.post_creates == 1
    assert openrouter.featured_image_calls == 0


def test_pipeline_resume_from_scraped_skips_rescrape(workdir: Path) -> None:
    storage = PostStorage(workdir)
    discovered = FakeScraper().discover_posts("https://facebook.com/page", 1, 0)[0]
    record = storage.build_record(discovered)
    storage.initialize(record, dry_run=False)
    (record.folder / "content.md").write_text("konten asli\n", encoding="utf-8")
    (record.folder / "images" / "image-1.jpg").write_bytes(b"image-bytes")
    storage.write_status(record.folder, stage=Stage.FAILED, dry_run=False, last_error="redact failed")

    scraper = FakeScraper()
    scraper.scrape_calls = 0

    original_scrape_post = scraper.scrape_post

    def counted_scrape_post(post):
        scraper.scrape_calls += 1
        return original_scrape_post(post)

    scraper.scrape_post = counted_scrape_post
    wordpress = FakeWordPress()
    openrouter = FakeOpenRouter()
    pipeline = PostPipeline(storage, scraper, openrouter, wordpress)
    pipeline.process_post(discovered, dry_run=False)

    status = json.loads((record.folder / "status.json").read_text(encoding="utf-8"))
    assert status["stage"] == "published"
    assert scraper.scrape_calls == 0
    assert openrouter.featured_image_calls == 0


def test_pipeline_without_openrouter_stops_after_scrape(workdir: Path) -> None:
    storage = PostStorage(workdir)
    pipeline = PostPipeline(storage, FakeScraper(), None, FakeWordPress())
    pipeline.run("https://facebook.com/page", count=1, skip=0, dry_run=False)
    folder = next(workdir.iterdir())
    status = json.loads((folder / "status.json").read_text(encoding="utf-8"))
    assert status["stage"] == "scraped"
    assert not (folder / "content-redacted.md").exists()


def test_pipeline_without_wordpress_stops_after_redact(workdir: Path) -> None:
    storage = PostStorage(workdir)
    pipeline = PostPipeline(storage, FakeScraper(), FakeOpenRouter(), None)
    pipeline.run("https://facebook.com/page", count=1, skip=0, dry_run=False)
    folder = next(workdir.iterdir())
    status = json.loads((folder / "status.json").read_text(encoding="utf-8"))
    assert status["stage"] == "redacted"
    assert (folder / "content-redacted.md").exists()


def test_pipeline_selects_featured_image_for_multiple_images(workdir: Path) -> None:
    class MultiImageScraper(FakeScraper):
        def scrape_post(self, discovered: DiscoveredPost):
            from fbpost_to_wordpress.models import ScrapedPost

            return ScrapedPost(
                post_id=discovered.post_id,
                post_url=discovered.post_url,
                page_url=discovered.page_url,
                content="konten asli",
                published_at=discovered.published_at,
                images=[
                    "https://example.com/image-1.jpg",
                    "https://example.com/image-2.jpg",
                ],
            )

    storage = PostStorage(workdir)
    openrouter = FakeOpenRouter()
    wordpress = FakeWordPress()
    pipeline = PostPipeline(storage, MultiImageScraper(), openrouter, wordpress)
    pipeline.run("https://facebook.com/page", count=1, skip=0, dry_run=False)

    folder = next(workdir.iterdir())
    selection = json.loads((folder / "featured-image.json").read_text(encoding="utf-8"))
    assert selection["selected_image"] == "image-2.jpg"
    assert openrouter.featured_image_calls == 1
    assert wordpress.featured_media_ids == [100]


def test_pipeline_saves_fallback_featured_image_when_selection_fails(workdir: Path) -> None:
    class MultiImageScraper(FakeScraper):
        def scrape_post(self, discovered: DiscoveredPost):
            from fbpost_to_wordpress.models import ScrapedPost

            return ScrapedPost(
                post_id=discovered.post_id,
                post_url=discovered.post_url,
                page_url=discovered.page_url,
                content="konten asli",
                published_at=discovered.published_at,
                images=[
                    "https://example.com/image-1.jpg",
                    "https://example.com/image-2.jpg",
                ],
            )

    class FailingOpenRouter(FakeOpenRouter):
        def select_featured_image(self, content: str, image_paths: list[Path]):
            raise ValueError("rate limited")

    storage = PostStorage(workdir)
    pipeline = PostPipeline(storage, MultiImageScraper(), FailingOpenRouter(), FakeWordPress())
    pipeline.run("https://facebook.com/page", count=1, skip=0, dry_run=False)

    folder = next(workdir.iterdir())
    selection = json.loads((folder / "featured-image.json").read_text(encoding="utf-8"))
    assert selection["selected_image"] == "image-1.jpg"
    assert "Fallback to first image" in selection["reason"]


def test_pipeline_updates_existing_wordpress_draft_with_same_source_id(workdir: Path) -> None:
    storage = PostStorage(workdir)
    wordpress = FakeWordPress()
    wordpress.find_result = WordPressPostRef(id=555, status="draft")
    pipeline = PostPipeline(storage, FakeScraper(), FakeOpenRouter(), wordpress)
    pipeline.run("https://facebook.com/page", count=1, skip=0, dry_run=False)

    folder = next(workdir.iterdir())
    status = json.loads((folder / "status.json").read_text(encoding="utf-8"))
    assert status["stage"] == "published"
    assert status["wordpress_post_id"] == 555
    assert wordpress.post_creates == 0
    assert wordpress.post_updates == 1
    assert wordpress.updated_source_ids == ["123"]


def test_pipeline_skips_existing_published_wordpress_post_with_same_source_id(workdir: Path) -> None:
    storage = PostStorage(workdir)
    wordpress = FakeWordPress()
    wordpress.find_result = WordPressPostRef(id=777, status="publish")
    pipeline = PostPipeline(storage, FakeScraper(), FakeOpenRouter(), wordpress)
    pipeline.run("https://facebook.com/page", count=1, skip=0, dry_run=False)

    folder = next(workdir.iterdir())
    status = json.loads((folder / "status.json").read_text(encoding="utf-8"))
    assert status["stage"] == "published"
    assert status["wordpress_post_id"] == 777
    assert wordpress.post_creates == 0
    assert wordpress.post_updates == 0
    assert wordpress.uploaded == []


def test_pipeline_run_post_folder_forces_requested_stage(workdir: Path) -> None:
    storage = PostStorage(workdir)
    discovered = FakeScraper().discover_posts("https://facebook.com/page", 1, 0)[0]
    record = storage.build_record(discovered)
    storage.initialize(record, dry_run=False)
    (record.folder / "content.md").write_text("konten asli\n", encoding="utf-8")
    (record.folder / "content-redacted.md").write_text("# Judul\n\nIsi\n", encoding="utf-8")
    (record.folder / "images" / "image-1.jpg").write_bytes(b"image-bytes")
    storage.write_status(record.folder, stage=Stage.PUBLISHED, dry_run=False, wordpress_post_id=999)

    wordpress = FakeWordPress()
    openrouter = FakeOpenRouter()
    pipeline = PostPipeline(storage, FakeScraper(), openrouter, wordpress)
    pipeline.run_post_folder(record.folder, dry_run=False, force_stage=Stage.REDACTED)

    status = json.loads((record.folder / "status.json").read_text(encoding="utf-8"))
    assert status["stage"] == "published"
    assert status["wordpress_post_id"] == 321
    assert wordpress.post_creates == 1


def test_pipeline_run_with_no_discovered_posts_exits_cleanly(workdir: Path) -> None:
    class EmptyScraper(FakeScraper):
        def discover_posts(self, page_url: str, count: int, skip: int):
            return []

    storage = PostStorage(workdir)
    pipeline = PostPipeline(storage, EmptyScraper(), FakeOpenRouter(), FakeWordPress())

    pipeline.run("https://facebook.com/page", count=2, skip=5, dry_run=False)

    assert list(workdir.iterdir()) == []
