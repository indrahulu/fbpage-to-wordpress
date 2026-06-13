import json
from pathlib import Path

import httpx
import pytest
import respx

from fbpost_to_wordpress.openrouter import OpenRouterClient


@respx.mock
def test_openrouter_redact_parses_markdown_response() -> None:
    route = respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": "# Judul Final\n\nIsi artikel yang sudah dirapikan."
                        }
                    }
                ]
            },
        )
    )

    client = OpenRouterClient(api_key="test-key", model="test-model")
    result = client.redact("konten sumber")

    assert route.called
    request = route.calls[0].request
    assert request.headers["Authorization"] == "Bearer test-key"
    assert request.url.path == "/api/v1/chat/completions"
    assert result.title == "Judul Final"
    assert "dirapikan" in result.body
    assert "Teks sumber:" in route.calls[0].request.content.decode("utf-8")


@respx.mock
def test_openrouter_redact_raises_for_invalid_markdown() -> None:
    respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={"choices": [{"message": {"content": "tanpa heading markdown"}}]},
        )
    )

    client = OpenRouterClient(api_key="test-key", model="test-model")
    with pytest.raises(ValueError):
        client.redact("konten sumber")


def test_openrouter_loads_prompt_from_file(workdir) -> None:
    prompt_path = workdir / "prompt-content-refine.md"
    prompt_path.write_text("Prompt kustom", encoding="utf-8")
    client = OpenRouterClient(api_key="test-key", model="test-model", prompt_path=prompt_path)
    assert client.load_prompt() == "Prompt kustom"


@respx.mock
def test_openrouter_select_featured_image_parses_fenced_json(workdir) -> None:
    featured_prompt = workdir / "prompt-featured-image.md"
    featured_prompt.write_text("Pilih featured image", encoding="utf-8")
    image_path = workdir / "image-1.jpg"
    image_path.write_bytes(b"fake-image")
    route = respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": "```json\n{\"selected_image\":\"image-1.jpg\",\"reason\":\"Paling jelas.\"}\n```"
                        }
                    }
                ]
            },
        )
    )

    client = OpenRouterClient(
        api_key="test-key",
        model="test-model",
        featured_image_prompt_path=featured_prompt,
    )
    result = client.select_featured_image("isi post", [image_path])

    assert route.called
    request_payload = json.loads(route.calls[0].request.content.decode("utf-8"))
    assert request_payload["messages"][1]["content"][1]["text"] == "Filename: image-1.jpg"
    assert result.selected_image == "image-1.jpg"
    assert result.reason == "Paling jelas."


@respx.mock
def test_openrouter_select_featured_image_rejects_unknown_filename(workdir: Path) -> None:
    featured_prompt = workdir / "prompt-featured-image.md"
    featured_prompt.write_text("Pilih featured image", encoding="utf-8")
    image_path = workdir / "image-1.jpg"
    image_path.write_bytes(b"fake-image")
    respx.post("https://openrouter.ai/api/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "content": "{\"selected_image\":\"image-9.jpg\",\"reason\":\"Salah pilih.\"}"
                        }
                    }
                ]
            },
        )
    )

    client = OpenRouterClient(
        api_key="test-key",
        model="test-model",
        featured_image_prompt_path=featured_prompt,
    )
    with pytest.raises(ValueError):
        client.select_featured_image("isi post", [image_path])
