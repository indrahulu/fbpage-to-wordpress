from __future__ import annotations

from pathlib import Path
from typing import Self, TypeVar

from dotenv import dotenv_values
from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator
from pydantic.alias_generators import to_pascal


WORDPRESS_POST_STATUSES = {"draft", "future", "pending", "private", "publish"}
ConfigModel = TypeVar("ConfigModel", bound=BaseModel)


def _load_model_from_env(model_cls: type[ConfigModel], env_path: str | Path) -> ConfigModel:
    env_values = dotenv_values(env_path)
    raw: dict[str, object] = {}
    for field_name, field_info in model_cls.model_fields.items():
        env_name = field_info.alias or field_name.upper()
        value = env_values.get(env_name)
        if value is not None:
            raw[field_name] = value
    try:
        return model_cls(**raw)
    except Exception as exc:
        raise ValueError(f"Invalid configuration. Details:\n{exc}") from exc


class AppConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=to_pascal)

    apify_token: str = Field(alias="APIFY_TOKEN", min_length=1)
    apify_actor_id: str = Field(default="apify/facebook-posts-scraper", alias="APIFY_ACTOR_ID")
    openrouter_api_key: str | None = Field(default=None, alias="OPENROUTER_API_KEY")
    openrouter_model: str | None = Field(default=None, alias="OPENROUTER_MODEL")
    wp_base_url: HttpUrl | None = Field(default=None, alias="WP_BASE_URL")
    wp_username: str | None = Field(default=None, alias="WP_USERNAME")
    wp_app_password: str | None = Field(default=None, alias="WP_APP_PASSWORD")
    wp_create_post_status: str = Field(default="draft", alias="WP_CREATE_POST_STATUS")
    wp_update_post_status: str = Field(default="draft", alias="WP_UPDATE_POST_STATUS")
    headless: bool = Field(default=True, alias="HEADLESS")
    output_dir: Path = Field(default=Path("output"), alias="OUTPUT_DIR")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    @field_validator("wp_create_post_status", "wp_update_post_status", mode="before")
    @classmethod
    def normalize_wordpress_post_status(cls, value: object) -> str:
        if value is None:
            return "draft"
        if isinstance(value, str):
            normalized = value.strip().lower()
            return normalized or "draft"
        return str(value).strip().lower()

    @model_validator(mode="after")
    def validate_partial_groups(self) -> Self:
        openrouter_values = [self.openrouter_api_key, self.openrouter_model]
        if any(openrouter_values) and not all(openrouter_values):
            raise ValueError("OPENROUTER_API_KEY and OPENROUTER_MODEL must both be set, or both left empty.")

        wordpress_values = [self.wp_base_url, self.wp_username, self.wp_app_password]
        if any(wordpress_values) and not all(wordpress_values):
            raise ValueError("WP_BASE_URL, WP_USERNAME, and WP_APP_PASSWORD must all be set, or all left empty.")

        for env_name, status in (
            ("WP_CREATE_POST_STATUS", self.wp_create_post_status),
            ("WP_UPDATE_POST_STATUS", self.wp_update_post_status),
        ):
            if status not in WORDPRESS_POST_STATUSES:
                allowed = ", ".join(sorted(WORDPRESS_POST_STATUSES))
                raise ValueError(f"{env_name} must be one of: {allowed}")
        return self

    @property
    def can_refine(self) -> bool:
        return bool(self.openrouter_api_key and self.openrouter_model)

    @property
    def can_publish(self) -> bool:
        return bool(self.wp_base_url and self.wp_username and self.wp_app_password)


class ScheduledConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True, alias_generator=to_pascal)

    fb_page_url: HttpUrl = Field(alias="SCHEDULED_FB_PAGE_URL")
    count: int = Field(alias="SCHEDULED_COUNT", ge=1)
    skip: int = Field(alias="SCHEDULED_SKIP", ge=0)
    ntfy_topic: str = Field(alias="SCHEDULED_NTFY_TOPIC", min_length=1)
    ntfy_server_url: HttpUrl = Field(default="https://ntfy.sh", alias="SCHEDULED_NTFY_SERVER_URL")
    ntfy_token: str | None = Field(default=None, alias="SCHEDULED_NTFY_TOKEN")

    @field_validator("ntfy_topic", mode="before")
    @classmethod
    def normalize_ntfy_topic(cls, value: object) -> str:
        if isinstance(value, str):
            normalized = value.strip()
            return normalized
        return str(value).strip()

    @field_validator("ntfy_token", mode="before")
    @classmethod
    def normalize_ntfy_token(cls, value: object) -> str | None:
        if value is None:
            return None
        if isinstance(value, str):
            normalized = value.strip()
            return normalized or None
        normalized = str(value).strip()
        return normalized or None


def load_config(env_path: str | Path = ".env") -> AppConfig:
    return _load_model_from_env(AppConfig, env_path)


def load_scheduled_config(env_path: str | Path = ".env") -> ScheduledConfig:
    return _load_model_from_env(ScheduledConfig, env_path)
