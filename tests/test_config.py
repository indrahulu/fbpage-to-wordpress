from pathlib import Path

import pytest

from fbpost_to_wordpress.config import load_config


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
