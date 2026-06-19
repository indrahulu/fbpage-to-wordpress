import httpx
import respx

from fbpost_to_wordpress.notifier import NtfyClient


@respx.mock
def test_ntfy_client_posts_title_and_body() -> None:
    route = respx.post("https://ntfy.sh/my-topic").mock(return_value=httpx.Response(200))

    client = NtfyClient(topic="my-topic")
    client.notify(title="Run selesai", message="Semua baik")

    assert route.called
    request = route.calls[0].request
    assert request.headers["Title"] == "Run selesai"
    assert request.content == b"Semua baik"
