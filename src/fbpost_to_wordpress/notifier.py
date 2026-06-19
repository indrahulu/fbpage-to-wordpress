from __future__ import annotations

from dataclasses import dataclass

import httpx


@dataclass(slots=True)
class NtfyClient:
    topic: str
    server_url: str = "https://ntfy.sh"
    token: str | None = None

    def __post_init__(self) -> None:
        self.topic = self.topic.strip()
        self.server_url = self.server_url.rstrip("/")
        if self.token is not None:
            normalized = self.token.strip()
            self.token = normalized or None

    def notify(self, title: str, message: str) -> None:
        headers = {
            "Title": title,
            "Content-Type": "text/plain; charset=utf-8",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"

        with httpx.Client(timeout=30) as client:
            response = client.post(
                f"{self.server_url}/{self.topic}",
                headers=headers,
                content=message.encode("utf-8"),
            )
            response.raise_for_status()
