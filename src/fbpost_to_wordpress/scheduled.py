from __future__ import annotations

from rich.console import Console

from fbpost_to_wordpress.config import load_config, load_scheduled_config
from fbpost_to_wordpress.facebook import FacebookScraper
from fbpost_to_wordpress.notifier import NtfyClient
from fbpost_to_wordpress.openrouter import OpenRouterClient
from fbpost_to_wordpress.pipeline import PostPipeline
from fbpost_to_wordpress.storage import PostStorage
from fbpost_to_wordpress.wordpress import WordPressClient


def main() -> int:
    console = Console()

    try:
        app_config = load_config()
        scheduled_config = load_scheduled_config()
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        return 1

    if not app_config.can_refine:
        console.print("[yellow]OpenRouter config is incomplete. Refine stage will be skipped.[/yellow]")
    if not app_config.can_publish:
        console.print("[yellow]WordPress config is incomplete. Publish stage will be skipped.[/yellow]")

    storage = PostStorage(app_config.output_dir)
    scraper = FacebookScraper(token=app_config.apify_token, actor_id=app_config.apify_actor_id)
    openrouter_client = (
        OpenRouterClient(app_config.openrouter_api_key, app_config.openrouter_model)
        if app_config.can_refine
        else None
    )
    wordpress_client = (
        WordPressClient(
            str(app_config.wp_base_url),
            app_config.wp_username,
            app_config.wp_app_password,
            create_post_status=app_config.wp_create_post_status,
            update_post_status=app_config.wp_update_post_status,
        )
        if app_config.can_publish
        else None
    )
    notifier = NtfyClient(
        topic=scheduled_config.ntfy_topic,
        server_url=str(scheduled_config.ntfy_server_url),
        token=scheduled_config.ntfy_token,
    )
    pipeline = PostPipeline(storage, scraper, openrouter_client, wordpress_client, console=console)

    try:
        summary = pipeline.run(
            page_url=str(scheduled_config.fb_page_url),
            count=scheduled_config.count,
            skip=scheduled_config.skip,
            dry_run=False,
        )
    except Exception as exc:
        _notify_safe(
            notifier,
            console,
            title="fbpost-to-wordpress scheduled run failed",
            message=f"Scheduled run crashed before completion.\nError: {exc}",
        )
        console.print(f"[red]Scheduled run failed: {exc}[/red]")
        return 1

    if summary.failed_posts > 0:
        _notify_safe(
            notifier,
            console,
            title="fbpost-to-wordpress scheduled run completed with failures",
            message=(
                "Scheduled run finished with failures.\n"
                f"Page: {scheduled_config.fb_page_url}\n"
                f"Requested: {scheduled_config.count}\n"
                f"Processed: {summary.discovered_posts}\n"
                f"Succeeded: {summary.succeeded_posts}\n"
                f"Failed: {summary.failed_posts}"
            ),
        )
        console.print(
            f"[red]Scheduled run completed with {summary.failed_posts} failure(s).[/red]"
        )
        return 1

    _notify_safe(
        notifier,
        console,
        title="fbpost-to-wordpress scheduled run completed",
        message=(
            "Scheduled run finished successfully.\n"
            f"Page: {scheduled_config.fb_page_url}\n"
            f"Requested: {scheduled_config.count}\n"
            f"Processed: {summary.discovered_posts}\n"
            f"Succeeded: {summary.succeeded_posts}\n"
            f"Failed: {summary.failed_posts}"
        ),
    )
    console.print("[green]Scheduled run completed successfully.[/green]")
    return 0


def _notify_safe(notifier: NtfyClient, console: Console, title: str, message: str) -> None:
    try:
        notifier.notify(title=title, message=message)
    except Exception as exc:
        console.print(f"[yellow]Failed to send ntfy notification: {exc}[/yellow]")


if __name__ == "__main__":
    raise SystemExit(main())
