from __future__ import annotations

import json
from pathlib import Path

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from fbpost_to_wordpress.models import FeaturedImageCandidate, FeaturedImageSelection, RedactedContent
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
    def select_featured_image(self, content: str, candidates: list[FeaturedImageCandidate]) -> FeaturedImageSelection:
        if not candidates:
            raise ValueError("At least one image is required to select a featured image.")

        prompt = self.load_prompt(self.featured_image_prompt_path)
        candidate_lines = "\n".join(f"- {candidate.filename}: {candidate.public_url}" for candidate in candidates)
        message_content = [
            {
                "type": "text",
                "text": (
                    f"{prompt}\n\n"
                    f"Konten post:\n---\n{content.strip()}\n---\n\n"
                    f"Kandidat gambar:\n{candidate_lines}\n\n"
                    "Pilih satu kandidat dan kembalikan JSON saja. "
                    "Gunakan format berikut:\n"
                    '{ "selected_image": "image-x.jpg", "selected_url": "https://...", "reason": "..." }\n'
                    "selected_image wajib diisi dengan filename persis dari daftar. "
                    "selected_url wajib diisi dengan public URL yang cocok untuk kandidat terpilih. "
                    "Jika memilih berdasarkan URL, selected_image dan selected_url harus menunjuk ke kandidat yang sama."
                ),
            }
        ]

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
        selected_image = str(parsed.get("selected_image", "")).strip()
        selected_url_raw = parsed.get("selected_url")
        selected_url = str(selected_url_raw).strip() if selected_url_raw is not None else None
        reason = str(parsed["reason"]).strip()
        candidates_by_name = {candidate.filename: candidate for candidate in candidates}
        if selected_image not in candidates_by_name:
            raise ValueError(f"Selected image is not in local candidates: {selected_image}")
        if selected_url is None:
            selected_url = candidates_by_name[selected_image].public_url
        selection = FeaturedImageSelection(
            selected_image=selected_image,
            reason=reason,
            selected_url=selected_url,
            source="ai",
            model=self.model,
        )
        matched_candidate = candidates_by_name[selection.selected_image]
        if selection.selected_url != matched_candidate.public_url:
            raise ValueError(f"Selected image and URL do not match the same candidate: {selection.selected_image}")
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
