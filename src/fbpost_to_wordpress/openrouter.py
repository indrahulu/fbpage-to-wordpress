from __future__ import annotations

import base64
import json
from pathlib import Path

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from fbpost_to_wordpress.models import FeaturedImageSelection, RedactedContent
from fbpost_to_wordpress.utils import parse_redacted_markdown


class OpenRouterClient:
    def __init__(
        self,
        api_key: str,
        model: str,
        prompt_path: str | Path = "prompt-content-refine.md",
        featured_image_prompt_path: str | Path = "prompt-featured-image.md",
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.prompt_path = Path(prompt_path)
        self.featured_image_prompt_path = Path(featured_image_prompt_path)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8), reraise=True)
    def redact(self, content: str) -> RedactedContent:
        prompt = self.load_prompt(self.prompt_path)
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "You are an editor that returns clean Markdown only."},
                {"role": "user", "content": f"{prompt}\n\nTeks sumber:\n\n{content}"},
            ],
        }
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://local.cli",
            "X-Title": "fbpost-to-wordpress",
        }
        with httpx.Client(base_url="https://openrouter.ai", timeout=90) as client:
            response = client.post("/api/v1/chat/completions", headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()
        markdown = data["choices"][0]["message"]["content"]
        return parse_redacted_markdown(markdown)

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=8), reraise=True)
    def select_featured_image(self, content: str, image_paths: list[Path]) -> FeaturedImageSelection:
        if not image_paths:
            raise ValueError("At least one image is required to select a featured image.")

        prompt = self.load_prompt(self.featured_image_prompt_path)
        message_content = [
            {
                "type": "text",
                "text": (
                    f"{prompt}\n\n"
                    f"Konten post:\n---\n{content.strip()}\n---\n\n"
                    f"Pilih hanya dari file berikut: {', '.join(path.name for path in image_paths)}\n"
                    "Kembalikan JSON saja."
                ),
            }
        ]
        for path in image_paths:
            encoded = base64.b64encode(path.read_bytes()).decode("ascii")
            mime_type = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
            message_content.append({"type": "text", "text": f"Filename: {path.name}"})
            message_content.append(
                {
                    "type": "image_url",
                    "image_url": {"url": f"data:{mime_type};base64,{encoded}"},
                }
            )

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "You choose one featured image and return JSON only."},
                {"role": "user", "content": message_content},
            ],
        }
        with httpx.Client(base_url="https://openrouter.ai", timeout=120) as client:
            response = client.post("/api/v1/chat/completions", headers=self._headers(), json=payload)
            response.raise_for_status()
            data = response.json()
        raw_content = data["choices"][0]["message"]["content"]
        cleaned = self._strip_code_fences(raw_content)
        parsed = json.loads(cleaned)
        selection = FeaturedImageSelection(
            selected_image=parsed["selected_image"].strip(),
            reason=parsed["reason"].strip(),
        )
        available_names = {path.name for path in image_paths}
        if selection.selected_image not in available_names:
            raise ValueError(f"Selected image is not in local candidates: {selection.selected_image}")
        return selection

    def load_prompt(self, path: Path | None = None) -> str:
        target_path = path or self.prompt_path
        prompt = target_path.read_text(encoding="utf-8").strip()
        if not prompt:
            raise ValueError(f"Prompt file is empty: {target_path}")
        return prompt

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://local.cli",
            "X-Title": "fbpost-to-wordpress",
        }

    def _strip_code_fences(self, text: str) -> str:
        stripped = text.strip()
        if stripped.startswith("```") and stripped.endswith("```"):
            lines = stripped.splitlines()
            if len(lines) >= 3:
                return "\n".join(lines[1:-1]).strip()
        return stripped
