import json
from datetime import UTC, datetime
from pathlib import Path

from fbpost_to_wordpress.models import DiscoveredPost, FeaturedImageSelection, Stage
from fbpost_to_wordpress.storage import PostStorage


def test_storage_initializes_status_and_metadata(workdir: Path) -> None:
    storage = PostStorage(workdir)
    record = storage.build_record(
        DiscoveredPost(
            post_id="123",
            post_url="https://facebook.com/posts/123",
            page_url="https://facebook.com/page",
            published_at=datetime(2024, 5, 6, 7, 8, tzinfo=UTC),
        )
    )
    storage.initialize(record, dry_run=True)
    status = json.loads((record.folder / "status.json").read_text(encoding="utf-8"))
    assert status["stage"] == Stage.DISCOVERED
    assert (record.folder / "metadata.md").exists()


def test_storage_lists_images(workdir: Path) -> None:
    folder = workdir / "post"
    images = folder / "images"
    images.mkdir(parents=True)
    (images / "b.jpg").write_bytes(b"b")
    (images / "a.jpg").write_bytes(b"a")
    storage = PostStorage(workdir)
    listed = storage.list_local_images(folder)
    assert [path.name for path in listed] == ["a.jpg", "b.jpg"]


def test_storage_writes_and_reads_featured_image_selection(workdir: Path) -> None:
    storage = PostStorage(workdir)
    record = storage.build_record(
        DiscoveredPost(
            post_id="123",
            post_url="https://facebook.com/posts/123",
            page_url="https://facebook.com/page",
            published_at=None,
        )
    )
    storage.initialize(record, dry_run=False)
    selection = FeaturedImageSelection(
        selected_image="image-2.jpg",
        selected_url="https://example.com/uploads/image-2.jpg",
        reason="Paling jelas",
        source="ai",
        model="test-model",
    )

    storage.write_featured_image_selection(record, selection)

    written = json.loads((record.folder / "featured-image.json").read_text(encoding="utf-8"))
    assert written == {
        "selected_image": "image-2.jpg",
        "selected_url": "https://example.com/uploads/image-2.jpg",
        "reason": "Paling jelas",
        "source": "ai",
        "model": "test-model",
    }

    loaded = storage.read_featured_image_selection(record.folder)
    assert loaded == selection


def test_storage_reads_legacy_featured_image_selection(workdir: Path) -> None:
    folder = workdir / "post"
    folder.mkdir(parents=True)
    (folder / "featured-image.json").write_text(
        json.dumps(
            {
                "selected_image": "image-1.jpg",
                "selected_url": "https://example.com/uploads/image-1.jpg",
                "reason": "Paling jelas",
            }
        ),
        encoding="utf-8",
    )

    storage = PostStorage(workdir)
    selection = storage.read_featured_image_selection(folder)

    assert selection == FeaturedImageSelection(
        selected_image="image-1.jpg",
        selected_url="https://example.com/uploads/image-1.jpg",
        reason="Paling jelas",
    )
