import json
from datetime import UTC, datetime
from pathlib import Path

from fbpost_to_wordpress.models import DiscoveredPost, Stage
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
