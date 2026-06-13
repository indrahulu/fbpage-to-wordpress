import sys
from pathlib import Path

from fbpost_to_wordpress import cli


class DummyConfig:
    apify_token = "apify-token"
    apify_actor_id = "apify/facebook-posts-scraper"
    openrouter_api_key = None
    openrouter_model = None
    wp_base_url = None
    wp_username = None
    wp_app_password = None
    can_refine = False
    can_publish = False
    output_dir = Path("output")


class DummyPipeline:
    last_instance = None

    def __init__(self, *args, **kwargs):
        self.run_calls = []
        self.run_post_folder_calls = []
        DummyPipeline.last_instance = self

    def run(self, **kwargs):
        self.run_calls.append(kwargs)

    def run_post_folder(self, **kwargs):
        self.run_post_folder_calls.append(kwargs)


def test_cli_force_stage_requires_post_folder(monkeypatch) -> None:
    monkeypatch.setattr(cli, "load_config", lambda: DummyConfig())
    monkeypatch.setattr(cli, "PostPipeline", DummyPipeline)
    monkeypatch.setattr(sys, "argv", ["main.py", "--force-stage", "redacted"])

    exit_code = cli.main()

    assert exit_code == 1


def test_cli_post_folder_cannot_be_combined_with_page_args(monkeypatch, workdir: Path) -> None:
    monkeypatch.setattr(cli, "load_config", lambda: DummyConfig())
    monkeypatch.setattr(cli, "PostPipeline", DummyPipeline)
    folder = workdir / "post-folder"
    folder.mkdir()
    monkeypatch.setattr(
        sys,
        "argv",
        ["main.py", "--post-folder", str(folder), "--count", "1"],
    )

    exit_code = cli.main()

    assert exit_code == 1


def test_cli_runs_single_post_folder_mode(monkeypatch, workdir: Path) -> None:
    monkeypatch.setattr(cli, "load_config", lambda: DummyConfig())
    monkeypatch.setattr(cli, "PostPipeline", DummyPipeline)
    folder = workdir / "post-folder"
    folder.mkdir()
    monkeypatch.setattr(
        sys,
        "argv",
        ["main.py", "--post-folder", str(folder), "--force-stage", "redacted", "--dry-run"],
    )

    exit_code = cli.main()

    assert exit_code == 0
    assert DummyPipeline.last_instance is not None
    assert DummyPipeline.last_instance.run_calls == []
    assert DummyPipeline.last_instance.run_post_folder_calls == [
        {
            "folder": folder,
            "dry_run": True,
            "force_stage": cli.Stage.REDACTED,
        }
    ]
