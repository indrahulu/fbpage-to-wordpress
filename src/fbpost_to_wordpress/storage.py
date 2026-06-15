from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from fbpost_to_wordpress.models import DiscoveredPost, FeaturedImageSelection, PostRecord, ScrapedPost, Stage
from fbpost_to_wordpress.utils import build_post_folder_name, ensure_utc


@dataclass(slots=True)
class StatusState:
    stage: str
    dry_run: bool
    last_error: str | None = None
    wordpress_post_id: int | None = None
    wordpress_media_ids: list[int] | None = None
    updated_at: str | None = None


class PostStorage:
    def __init__(self, output_dir: Path) -> None:
        self.output_dir = output_dir
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def build_record(self, discovered: DiscoveredPost) -> PostRecord:
        folder_name = build_post_folder_name(discovered.published_at, discovered.post_id)
        folder = self.output_dir / folder_name
        return PostRecord(
            post_id=discovered.post_id,
            post_url=discovered.post_url,
            page_url=discovered.page_url,
            folder=folder,
            published_at=discovered.published_at,
        )

    def initialize(self, record: PostRecord, dry_run: bool) -> None:
        record.folder.mkdir(parents=True, exist_ok=True)
        (record.folder / "images").mkdir(exist_ok=True)
        metadata_path = record.folder / "metadata.md"
        if not metadata_path.exists():
            metadata_path.write_text(self._metadata_text(record, scraped_at=None, image_count=None), encoding="utf-8")
        if not (record.folder / "status.json").exists():
            self.write_status(record.folder, Stage.DISCOVERED, dry_run=dry_run)

    def write_scraped_content(self, record: PostRecord, scraped: ScrapedPost) -> None:
        record.folder.mkdir(parents=True, exist_ok=True)
        (record.folder / "content.md").write_text(scraped.content.strip() + "\n", encoding="utf-8")
        (record.folder / "metadata.md").write_text(
            self._metadata_text(record, scraped_at=datetime.now(tz=UTC), image_count=len(scraped.images)),
            encoding="utf-8",
        )

    def save_image(self, record: PostRecord, filename: str, content: bytes) -> Path:
        image_path = record.folder / "images" / filename
        image_path.write_bytes(content)
        return image_path

    def write_redacted_content(self, record: PostRecord, markdown: str) -> None:
        (record.folder / "content-redacted.md").write_text(markdown.rstrip() + "\n", encoding="utf-8")

    def write_publish_preview(self, record: PostRecord, markdown: str) -> None:
        (record.folder / "publish-preview.md").write_text(markdown.rstrip() + "\n", encoding="utf-8")

    def write_featured_image_selection(self, record: PostRecord, selection: FeaturedImageSelection) -> None:
        path = record.folder / "featured-image.json"
        payload = {
            key: value
            for key, value in asdict(selection).items()
            if value is not None
        }
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def read_featured_image_selection(self, folder: Path) -> FeaturedImageSelection | None:
        path = folder / "featured-image.json"
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError(f"Invalid featured image selection file: {path}")
        return FeaturedImageSelection(
            selected_image=str(data["selected_image"]),
            reason=str(data["reason"]),
            selected_url=str(data["selected_url"]) if data.get("selected_url") is not None else None,
            source=str(data["source"]) if data.get("source") is not None else None,
            model=str(data["model"]) if data.get("model") is not None else None,
        )

    def read_status(self, folder: Path) -> StatusState:
        path = folder / "status.json"
        if not path.exists():
            raise FileNotFoundError(f"Missing status file: {path}")
        data = json.loads(path.read_text(encoding="utf-8"))
        return StatusState(**data)

    def write_status(
        self,
        folder: Path,
        stage: Stage,
        dry_run: bool,
        last_error: str | None = None,
        wordpress_post_id: int | None = None,
        wordpress_media_ids: list[int] | None = None,
    ) -> None:
        state = StatusState(
            stage=stage.value,
            dry_run=dry_run,
            last_error=last_error,
            wordpress_post_id=wordpress_post_id,
            wordpress_media_ids=wordpress_media_ids,
            updated_at=datetime.now(tz=UTC).isoformat(),
        )
        (folder / "status.json").write_text(json.dumps(asdict(state), indent=2), encoding="utf-8")

    def existing_stage(self, folder: Path) -> Stage | None:
        path = folder / "status.json"
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        return Stage(data["stage"])

    def infer_resume_stage(self, folder: Path) -> Stage:
        current = self.existing_stage(folder)
        if current and current is not Stage.FAILED:
            return current
        if (folder / "content-redacted.md").exists():
            return Stage.REDACTED
        if (folder / "content.md").exists():
            return Stage.SCRAPED
        return Stage.DISCOVERED

    def list_local_images(self, folder: Path) -> list[Path]:
        images_dir = folder / "images"
        if not images_dir.exists():
            return []
        return sorted(path for path in images_dir.iterdir() if path.is_file())

    def read_record(self, folder: Path) -> PostRecord:
        metadata = (folder / "metadata.md").read_text(encoding="utf-8").splitlines()
        values = {}
        for line in metadata:
            if ": " in line:
                key, value = line.split(": ", 1)
                values[key] = value
        published_at = datetime.fromisoformat(values["published_at_local"]) if values.get("published_at_local") else None
        return PostRecord(
            post_id=values["facebook_post_id"],
            post_url=values["source_post_url"],
            page_url=values["source_page_url"],
            folder=folder,
            published_at=published_at,
        )

    def _metadata_text(
        self,
        record: PostRecord,
        scraped_at: datetime | None,
        image_count: int | None,
    ) -> str:
        published_at_utc = ensure_utc(record.published_at)
        lines = [
            f"source_page_url: {record.page_url}",
            f"source_post_url: {record.post_url}",
            f"facebook_post_id: {record.post_id}",
            f"published_at_iso: {published_at_utc.isoformat() if published_at_utc else ''}",
            f"published_at_local: {record.published_at.isoformat() if record.published_at else ''}",
            f"scraped_at_iso: {scraped_at.isoformat() if scraped_at else ''}",
            f"image_count: {image_count if image_count is not None else ''}",
        ]
        return "\n".join(lines) + "\n"
