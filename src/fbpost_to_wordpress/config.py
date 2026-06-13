from __future__ import annotations

from pathlib import Path
from typing import Self

from dotenv import dotenv_values
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, model_validator
from pydantic.alias_generators import to_pascal


class AppConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=to_pascal)

    apify_token: str = Field(alias="APIFY_TOKEN", min_length=1)
    apify_actor_id: str = Field(default="apify/facebook-posts-scraper", alias="APIFY_ACTOR_ID")
    openrouter_api_key: str | None = Field(default=None, alias="OPENROUTER_API_KEY")
    openrouter_model: str | None = Field(default=None, alias="OPENROUTER_MODEL")
    wp_base_url: HttpUrl | None = Field(default=None, alias="WP_BASE_URL")
    wp_username: str | None = Field(default=None, alias="WP_USERNAME")
    wp_app_password: str | None = Field(default=None, alias="WP_APP_PASSWORD")
    headless: bool = Field(default=True, alias="HEADLESS")
    output_dir: Path = Field(default=Path("output"), alias="OUTPUT_DIR")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    @model_validator(mode="after")
    def validate_partial_groups(self) -> Self:
        openrouter_values = [self.openrouter_api_key, self.openrouter_model]
        if any(openrouter_values) and not all(openrouter_values):
            raise ValueError("OPENROUTER_API_KEY and OPENROUTER_MODEL must both be set, or both left empty.")

        wordpress_values = [self.wp_base_url, self.wp_username, self.wp_app_password]
        if any(wordpress_values) and not all(wordpress_values):
            raise ValueError("WP_BASE_URL, WP_USERNAME, and WP_APP_PASSWORD must all be set, or all left empty.")
        return self

    @property
    def can_refine(self) -> bool:
        return bool(self.openrouter_api_key and self.openrouter_model)

    @property
    def can_publish(self) -> bool:
        return bool(self.wp_base_url and self.wp_username and self.wp_app_password)


def load_config(env_path: str | Path = ".env") -> AppConfig:
    env_values = dotenv_values(env_path)
    raw = {}
    for field_name, field_info in AppConfig.model_fields.items():
        env_name = field_info.alias or field_name.upper()
        value = env_values.get(env_name)
        if value is not None:
            raw[field_name] = value
    try:
        return AppConfig(**raw)
    except Exception as exc:
        raise ValueError(f"Invalid configuration. Details:\n{exc}") from exc
