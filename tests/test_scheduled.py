from pathlib import Path
from types import SimpleNamespace

from fbpost_to_wordpress import scheduled


class DummyPipeline:
    last_instance = None
    run_result = SimpleNamespace(discovered_posts=1, failed_posts=0, succeeded_posts=1)

    def __init__(self, *args, **kwargs):
        self.run_calls = []
        DummyPipeline.last_instance = self

    def run(self, **kwargs):
        self.run_calls.append(kwargs)
        return DummyPipeline.run_result


class DummyNtfyClient:
    last_instance = None

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.notifications = []
        DummyNtfyClient.last_instance = self

    def notify(self, title: str, message: str) -> None:
        self.notifications.append({"title": title, "message": message})


def _app_config(output_dir: Path) -> SimpleNamespace:
    return SimpleNamespace(
        apify_token="apify-token",
        apify_actor_id="apify/facebook-posts-scraper",
        openrouter_api_key=None,
        openrouter_model=None,
        wp_base_url=None,
        wp_username=None,
        wp_app_password=None,
        wp_create_post_status="draft",
        wp_update_post_status="draft",
        can_refine=False,
        can_publish=False,
        output_dir=output_dir,
    )


def _scheduled_config() -> SimpleNamespace:
    return SimpleNamespace(
        fb_page_url="https://facebook.com/page",
        count=2,
        skip=1,
        ntfy_topic="scheduled-topic",
        ntfy_server_url="https://ntfy.sh",
        ntfy_token=None,
    )


def test_scheduled_main_uses_scheduled_env_and_notifies_success(monkeypatch, workdir: Path) -> None:
    monkeypatch.setattr(scheduled, "load_config", lambda: _app_config(workdir / "output"))
    monkeypatch.setattr(scheduled, "load_scheduled_config", _scheduled_config)
    monkeypatch.setattr(scheduled, "PostPipeline", DummyPipeline)
    monkeypatch.setattr(scheduled, "NtfyClient", DummyNtfyClient)

    exit_code = scheduled.main()

    assert exit_code == 0
    assert DummyPipeline.last_instance is not None
    assert DummyPipeline.last_instance.run_calls == [
        {
            "page_url": "https://facebook.com/page",
            "count": 2,
            "skip": 1,
            "dry_run": False,
        }
    ]
    assert DummyNtfyClient.last_instance is not None
    assert DummyNtfyClient.last_instance.notifications[0]["title"] == "fbpost-to-wordpress scheduled run completed"
    assert "Succeeded: 1" in DummyNtfyClient.last_instance.notifications[0]["message"]


def test_scheduled_main_exits_nonzero_on_pipeline_failures(monkeypatch, workdir: Path) -> None:
    DummyPipeline.run_result = SimpleNamespace(discovered_posts=2, failed_posts=1, succeeded_posts=1)
    monkeypatch.setattr(scheduled, "load_config", lambda: _app_config(workdir / "output"))
    monkeypatch.setattr(scheduled, "load_scheduled_config", _scheduled_config)
    monkeypatch.setattr(scheduled, "PostPipeline", DummyPipeline)
    monkeypatch.setattr(scheduled, "NtfyClient", DummyNtfyClient)

    exit_code = scheduled.main()

    assert exit_code == 1
    assert DummyNtfyClient.last_instance.notifications[0]["title"] == "fbpost-to-wordpress scheduled run completed with failures"
    assert "Failed: 1" in DummyNtfyClient.last_instance.notifications[0]["message"]
    DummyPipeline.run_result = SimpleNamespace(discovered_posts=1, failed_posts=0, succeeded_posts=1)
