import pytest

from fbpost_to_wordpress.utils import parse_redacted_markdown


def test_parse_redacted_markdown_returns_title_and_body() -> None:
    parsed = parse_redacted_markdown("# Judul\n\nIsi artikel")
    assert parsed.title == "Judul"
    assert parsed.body == "Isi artikel"


def test_parse_redacted_markdown_requires_heading() -> None:
    with pytest.raises(ValueError):
        parse_redacted_markdown("Isi artikel tanpa heading")

