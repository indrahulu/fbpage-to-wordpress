from pathlib import Path

import pytest

from fbpost_to_wordpress.config import load_config, load_scheduled_config


def test_load_config_reads_env_file(workdir: Path) -> None:
    env_path = workdir / ".env"
    env_path.write_text(
        "\n".join(
            [
                "APIFY_TOKEN=apify-token",
                "OPENROUTER_API_KEY=test-key",
                "OPENROUTER_MODEL=test-model",
                "WP_BASE_URL=https://example.com",
                "WP_USERNAME=admin",
                "WP_APP_PASSWORD=secret",
                "WP_CREATE_POST_STATUS=publish",
                "WP_UPDATE_POST_STATUS=pending",
            ]
        ),
        encoding="utf-8",
    )
    config = load_config(env_path)
    assert config.apify_token == "apify-token"
    assert config.openrouter_api_key == "test-key"
    assert str(config.wp_base_url) == "https://example.com/"
    assert config.can_refine is True
    assert config.can_publish is True
    assert config.wp_create_post_status == "publish"
    assert config.wp_update_post_status == "pending"


def test_load_config_defaults_wordpress_statuses_when_empty(workdir: Path) -> None:
    env_path = workdir / ".env"
    env_path.write_text(
        "\n".join(
            [
                "APIFY_TOKEN=apify-token",
                "WP_BASE_URL=https://example.com",
                "WP_USERNAME=admin",
                "WP_APP_PASSWORD=secret",
                "WP_CREATE_POST_STATUS=",
                "WP_UPDATE_POST_STATUS=   ",
            ]
        ),
        encoding="utf-8",
    )
    config = load_config(env_path)
    assert config.wp_create_post_status == "draft"
    assert config.wp_update_post_status == "draft"


def test_load_config_raises_for_missing_fields(workdir: Path) -> None:
    env_path = workdir / ".env"
    env_path.write_text("APIFY_TOKEN=apify-token\nOPENROUTER_API_KEY=test-key", encoding="utf-8")
    with pytest.raises(ValueError):
        load_config(env_path)


def test_load_config_requires_apify_token(workdir: Path) -> None:
    env_path = workdir / ".env"
    env_path.write_text("", encoding="utf-8")
    with pytest.raises(ValueError):
        load_config(env_path)


def test_load_config_rejects_invalid_wordpress_status(workdir: Path) -> None:
    env_path = workdir / ".env"
    env_path.write_text(
        "\n".join(
            [
                "APIFY_TOKEN=apify-token",
                "WP_BASE_URL=https://example.com",
                "WP_USERNAME=admin",
                "WP_APP_PASSWORD=secret",
                "WP_CREATE_POST_STATUS=not-a-status",
            ]
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        load_config(env_path)


def test_load_scheduled_config_reads_env_file(workdir: Path) -> None:
    env_path = workdir / ".env"
    env_path.write_text(
        "\n".join(
            [
                "SCHEDULED_FB_PAGE_URL=https://facebook.com/example",
                "SCHEDULED_COUNT=3",
                "SCHEDULED_SKIP=2",
                "SCHEDULED_NTFY_TOPIC=my-topic",
                "SCHEDULED_NTFY_SERVER_URL=https://ntfy.sh",
                "SCHEDULED_NTFY_TOKEN=secret-token",
            ]
        ),
        encoding="utf-8",
    )
    config = load_scheduled_config(env_path)
    assert str(config.fb_page_url) == "https://facebook.com/example"
    assert config.count == 3
    assert config.skip == 2
    assert config.ntfy_topic == "my-topic"
    assert str(config.ntfy_server_url) == "https://ntfy.sh/"
    assert config.ntfy_token == "secret-token"


def test_load_scheduled_config_does_not_use_manual_env_names(workdir: Path) -> None:
    env_path = workdir / ".env"
    env_path.write_text(
        "\n".join(
            [
                "FB_PAGE_URL=https://facebook.com/example",
                "COUNT=3",
                "SKIP=2",
                "NTFY_TOPIC=my-topic",
            ]
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError):
        load_scheduled_config(env_path)
