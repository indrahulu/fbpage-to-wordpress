from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from datetime import datetime

from rich.console import Console

from fbpost_to_wordpress.facebook import FacebookScraper, image_extension_from_url
from fbpost_to_wordpress.models import DiscoveredPost, FeaturedImageCandidate, FeaturedImageSelection, Stage
from fbpost_to_wordpress.openrouter import OpenRouterClient
from fbpost_to_wordpress.storage import PostStorage
from fbpost_to_wordpress.utils import parse_redacted_markdown
from fbpost_to_wordpress.wordpress import WordPressClient


@dataclass(slots=True)
class PipelineRunSummary:
    discovered_posts: int
    failed_posts: int

    @property
    def succeeded_posts(self) -> int:
        return self.discovered_posts - self.failed_posts


class PostPipeline:
    def __init__(
        self,
        storage: PostStorage,
        scraper: FacebookScraper,
        openrouter_client: OpenRouterClient | None,
        wordpress_client: WordPressClient | None,
        console: Console | None = None,
    ) -> None:
        self.storage = storage
        self.scraper = scraper
        self.openrouter_client = openrouter_client
        self.wordpress_client = wordpress_client
        self.console = console or Console()

    def run(self, page_url: str, count: int, skip: int, dry_run: bool) -> PipelineRunSummary:
        self.console.print(f"[cyan]Discovering posts from {page_url} (count={count}, skip={skip})[/cyan]")
        discovered_posts = self.scraper.discover_posts(page_url=page_url, count=count, skip=skip)
        summary = PipelineRunSummary(discovered_posts=len(discovered_posts), failed_posts=0)
        if not discovered_posts:
            self.console.print(
                f"[yellow]No posts available for requested skip={skip}, count={count}. Nothing to process.[/yellow]"
            )
            return summary
        if len(discovered_posts) < count:
            self.console.print(
                f"[yellow]Only {len(discovered_posts)} post(s) available after skip={skip}; requested {count}.[/yellow]"
            )
        self.console.print(f"[cyan]Discovered {len(discovered_posts)} post(s) to process[/cyan]")
        for index, discovered in enumerate(discovered_posts, start=1):
            self.console.print(f"[cyan]Processing post {index}/{len(discovered_posts)}: {discovered.post_id}[/cyan]")
            if not self.process_post(discovered, dry_run=dry_run):
                summary.failed_posts += 1
        return summary

    def run_post_folder(self, folder: Path, dry_run: bool, force_stage: Stage | None = None) -> None:
        record = self.storage.read_record(folder)
        discovered = DiscoveredPost(
            post_id=record.post_id,
            post_url=record.post_url,
            page_url=record.page_url,
            published_at=record.published_at,
        )
        if force_stage is not None:
            self.console.print(f"[yellow]Forcing stage for {record.post_id}: {force_stage.value}[/yellow]")
            self.storage.write_status(folder, force_stage, dry_run=dry_run)
        else:
            resume_stage = self.storage.infer_resume_stage(folder)
            self.console.print(f"[cyan]Resuming {record.post_id} from stage: {resume_stage.value}[/cyan]")
        self.process_post(discovered, dry_run=dry_run)

    def process_post(self, discovered: DiscoveredPost, dry_run: bool) -> bool:
        record = self.storage.build_record(discovered)
        self.storage.initialize(record, dry_run=dry_run)
        stage = self.storage.infer_resume_stage(record.folder)

        try:
            if stage is Stage.DISCOVERED:
                self.console.print(f"[blue]Scraping post {discovered.post_id}[/blue]")
                self._scrape_stage(discovered, record.folder, dry_run=dry_run)
                stage = Stage.SCRAPED
            if stage is Stage.SCRAPED:
                if self.openrouter_client is None:
                    self.console.print(f"[yellow]Skipping refine for {discovered.post_id}: OpenRouter config is incomplete[/yellow]")
                    return True
                self.console.print(f"[blue]Refining content for {discovered.post_id}[/blue]")
                self._redact_stage(record.folder, dry_run=dry_run)
                stage = Stage.REDACTED
            if dry_run:
                redacted_markdown = (record.folder / "content-redacted.md").read_text(encoding="utf-8")
                self.storage.write_publish_preview(record, redacted_markdown)
                self.console.print(f"[yellow]Dry-run: skipping publish for {discovered.post_id}[/yellow]")
                return True
            if stage is Stage.REDACTED:
                if self.wordpress_client is None:
                    self.console.print(f"[yellow]Skipping publish for {discovered.post_id}: WordPress config is incomplete[/yellow]")
                    return True
                self.console.print(f"[blue]Publishing {discovered.post_id} to WordPress[/blue]")
                self._publish_stage(record.folder, dry_run=dry_run, published_at=record.published_at)
                self.console.print(f"[green]Published {discovered.post_id} to WordPress[/green]")
            return True
        except Exception as exc:
            self.storage.write_status(record.folder, Stage.FAILED, dry_run=dry_run, last_error=str(exc))
            self.console.print(f"[red]Failed {discovered.post_id}: {exc}[/red]")
            return False

    def _scrape_stage(self, discovered: DiscoveredPost, folder: Path, dry_run: bool) -> None:
        scraped = self.scraper.scrape_post(discovered)
        record = self.storage.build_record(discovered)
        record.folder = folder
        self.storage.write_scraped_content(record, scraped)
        self.console.print(f"[blue]Saving scraped text for {discovered.post_id}[/blue]")
        self.console.print(f"[blue]Downloading {len(scraped.images)} image(s) for {discovered.post_id}[/blue]")
        for index, image_url in enumerate(scraped.images, start=1):
            filename = f"image-{index}.{image_extension_from_url(image_url)}"
            image_bytes = self.scraper.download_image(image_url)
            self.storage.save_image(record, filename, image_bytes)
        self.storage.write_status(folder, Stage.SCRAPED, dry_run=dry_run)
        self.console.print(f"[green]Scrape complete for {discovered.post_id}[/green]")

    def _redact_stage(self, folder: Path, dry_run: bool) -> None:
        content = (folder / "content.md").read_text(encoding="utf-8")
        redacted = self.openrouter_client.redact(content)
        self.storage.write_redacted_content(self.storage.read_record(folder), redacted.raw_markdown)
        self.storage.write_status(folder, Stage.REDACTED, dry_run=dry_run)
        self.console.print(f"[green]Refine complete for {self.storage.read_record(folder).post_id}[/green]")

    def _publish_stage(self, folder: Path, dry_run: bool, published_at) -> None:
        record = self.storage.read_record(folder)
        redacted = parse_redacted_markdown((folder / "content-redacted.md").read_text(encoding="utf-8"))
        images = self.storage.list_local_images(folder)
        existing_post = self.wordpress_client.find_post_by_source_id(record.post_id)
        if existing_post is not None and existing_post.status == "publish":
            self.console.print(
                f"[yellow]Skipping publish for {record.post_id}: existing published WordPress post #{existing_post.id} found[/yellow]"
            )
            self.storage.write_status(
                folder,
                Stage.PUBLISHED,
                dry_run=dry_run,
                wordpress_post_id=existing_post.id,
            )
            return
        self.console.print(f"[blue]Uploading {len(images)} image(s) to WordPress[/blue]")
        media_map = {path.name: self.wordpress_client.upload_media(path) for path in images}
        media_items = [media_map[path.name] for path in images]
        media_ids = [media.id for media in media_items]
        featured_image_name = self._resolve_featured_image_name(folder, images, media_map)
        featured_media_id = media_map.get(featured_image_name).id if featured_image_name and featured_image_name in media_map else None
        if featured_media_id is not None:
            self.console.print(f"[blue]Using {featured_image_name} as featured image[/blue]")
        if existing_post is not None:
            self.console.print(
                f"[blue]Updating existing WordPress {existing_post.status} #{existing_post.id} for {record.post_id}[/blue]"
            )
            post_id = self.wordpress_client.update_post(
                existing_post.id,
                redacted,
                media_items=media_items,
                source_post_id=record.post_id,
                source_post_url=record.post_url,
                published_at=published_at,
                featured_media_id=featured_media_id,
            )
        else:
            post_id = self.wordpress_client.create_post(
                redacted,
                media_items=media_items,
                source_post_id=record.post_id,
                source_post_url=record.post_url,
                published_at=published_at,
                featured_media_id=featured_media_id,
            )
        self.storage.write_status(
            folder,
            Stage.PUBLISHED,
            dry_run=dry_run,
            wordpress_post_id=post_id,
            wordpress_media_ids=media_ids,
        )

    def _resolve_featured_image_name(
        self,
        folder: Path,
        images: list[Path],
        media_map: dict[str, "WordPressMedia"],
    ) -> str | None:
        if not images:
            return None
        if len(images) == 1:
            selected = FeaturedImageSelection(
                selected_image=images[0].name,
                reason="Only one image available, so it is used as the featured image.",
                selected_url=media_map[images[0].name].source_url if images[0].name in media_map else None,
                source="fallback",
                model=getattr(self.openrouter_client, "model", None),
            )
            self._print_featured_image_decision(selected, source="fallback")
            return selected.selected_image

        existing = self.storage.read_featured_image_selection(folder)
        if existing is not None:
            source = existing.source or self._infer_featured_image_source(existing.reason)
            self._print_featured_image_decision(existing, source=source, reused=True)
            return existing.selected_image

        if self.openrouter_client is None:
            fallback = FeaturedImageSelection(
                selected_image=images[0].name,
                reason="OpenRouter config is incomplete, so the first image is used as the featured image.",
                selected_url=media_map[images[0].name].source_url if images[0].name in media_map else None,
                source="fallback",
                model=None,
            )
            self._print_featured_image_decision(fallback, source="fallback")
            return fallback.selected_image

        self.console.print(f"[blue]Selecting featured image from {len(images)} candidate(s)[/blue]")
        content = (folder / "content.md").read_text(encoding="utf-8")
        candidates = [
            FeaturedImageCandidate(filename=path.name, public_url=media_map[path.name].source_url)
            for path in images
            if path.name in media_map
        ]
        try:
            selection = self.openrouter_client.select_featured_image(content, candidates)
            selection = self._annotate_featured_image_selection(selection, source="ai")
            self.storage.write_featured_image_selection(self.storage.read_record(folder), selection)
            self._print_featured_image_decision(selection, source="ai")
            return selection.selected_image
        except Exception as exc:
            fallback = images[0].name
            fallback_selection = FeaturedImageSelection(
                selected_image=fallback,
                reason=f"Fallback to first image because automatic selection failed: {exc}",
                selected_url=media_map[fallback].source_url if fallback in media_map else None,
                source="fallback",
                model=getattr(self.openrouter_client, "model", None),
            )
            self.storage.write_featured_image_selection(
                self.storage.read_record(folder),
                fallback_selection,
            )
            self.console.print(f"[yellow]Featured image selection failed: {exc}. Falling back to {fallback}[/yellow]")
            self._print_featured_image_decision(
                fallback_selection,
                source="fallback",
            )
            return fallback

    def _annotate_featured_image_selection(self, selection: FeaturedImageSelection, source: str) -> FeaturedImageSelection:
        model = getattr(self.openrouter_client, "model", None)
        if selection.source == source and selection.model == model:
            return selection
        return FeaturedImageSelection(
            selected_image=selection.selected_image,
            reason=selection.reason,
            selected_url=selection.selected_url,
            source=source,
            model=model,
        )

    def _print_featured_image_decision(
        self,
        selection: FeaturedImageSelection,
        source: str,
        reused: bool = False,
    ) -> None:
        source_label = {
            "ai": "AI response",
            "fallback": "fallback",
        }.get(source, source)
        reused_label = "reused " if reused else ""
        details = [f"selected={selection.selected_image}"]
        if selection.selected_url:
            details.append(f"url={selection.selected_url}")
        details.append(f"reason={selection.reason}")
        self.console.print(
            f"[green]Featured image ({reused_label}from {source_label}): " + "; ".join(details) + "[/green]"
        )

    def _infer_featured_image_source(self, reason: str) -> str:
        if reason.lower().startswith("fallback to"):
            return "fallback"
        return "ai"
