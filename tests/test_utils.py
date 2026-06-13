from datetime import UTC, datetime

from fbpost_to_wordpress.utils import build_post_folder_name, extract_post_id_from_url


def test_build_post_folder_name_uses_date_and_post_id() -> None:
    name = build_post_folder_name(datetime(2024, 5, 6, 7, 8, tzinfo=UTC), "123456789")
    assert name == "2024-05-06-123456789"


def test_extract_post_id_from_url_supports_story_fbid() -> None:
    post_id = extract_post_id_from_url("https://www.facebook.com/story.php?story_fbid=12345&id=67890")
    assert post_id == "12345"

