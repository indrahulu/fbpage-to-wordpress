from __future__ import annotations

import argparse
from pathlib import Path

from rich.console import Console
from rich.prompt import IntPrompt, Prompt

from fbpost_to_wordpress.config import load_config
from fbpost_to_wordpress.facebook import FacebookScraper
from fbpost_to_wordpress.models import Stage
from fbpost_to_wordpress.openrouter import OpenRouterClient
from fbpost_to_wordpress.pipeline import PostPipeline
from fbpost_to_wordpress.storage import PostStorage
from fbpost_to_wordpress.wordpress import WordPressClient


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Scrape public Facebook posts and publish to WordPress.")
    parser.add_argument("--dry-run", action="store_true", help="Run scrape and redaction, but skip WordPress publish.")
    parser.add_argument("--page-url", help="Optional Facebook page URL to avoid interactive prompt.")
    parser.add_argument("--count", type=int, help="Optional number of posts to take.")
    parser.add_argument("--skip", type=int, help="Optional number of latest posts to skip.")
    parser.add_argument("--post-folder", help="Process one existing local post folder instead of discovering posts.")
    parser.add_argument(
        "--force-stage",
        choices=[Stage.DISCOVERED.value, Stage.SCRAPED.value, Stage.REDACTED.value],
        help="Force one existing local post folder to resume from a specific stage.",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    console = Console()

    try:
        config = load_config()
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        return 1

    if not config.can_refine:
        console.print("[yellow]OpenRouter config is incomplete. Refine stage will be skipped.[/yellow]")
    if not config.can_publish:
        console.print("[yellow]WordPress config is incomplete. Publish stage will be skipped.[/yellow]")

    if args.force_stage and not args.post_folder:
        console.print("[red]--force-stage requires --post-folder.[/red]")
        return 1
    if args.post_folder and any(value is not None for value in (args.page_url, args.count, args.skip)):
        console.print("[red]--post-folder cannot be combined with --page-url, --count, or --skip.[/red]")
        return 1

    storage = PostStorage(config.output_dir)
    scraper = FacebookScraper(token=config.apify_token, actor_id=config.apify_actor_id)
    openrouter_client = (
        OpenRouterClient(config.openrouter_api_key, config.openrouter_model)
        if config.can_refine
        else None
    )
    wordpress_client = (
        WordPressClient(str(config.wp_base_url), config.wp_username, config.wp_app_password)
        if config.can_publish
        else None
    )
    pipeline = PostPipeline(storage, scraper, openrouter_client, wordpress_client, console=console)
    if args.post_folder:
        folder = Path(args.post_folder)
        if not folder.exists() or not folder.is_dir():
            console.print(f"[red]post folder not found: {folder}[/red]")
            return 1
        force_stage = Stage(args.force_stage) if args.force_stage else None
        pipeline.run_post_folder(folder=folder, dry_run=args.dry_run, force_stage=force_stage)
        return 0

    page_url = args.page_url or Prompt.ask("Facebook page URL")
    count = args.count if args.count is not None else IntPrompt.ask("How many posts to fetch", default=1)
    skip = args.skip if args.skip is not None else IntPrompt.ask("How many latest posts to skip", default=0)

    if count <= 0:
        console.print("[red]count must be greater than zero.[/red]")
        return 1
    if skip < 0:
        console.print("[red]skip must be zero or positive.[/red]")
        return 1

    pipeline.run(page_url=page_url, count=count, skip=skip, dry_run=args.dry_run)
    return 0
