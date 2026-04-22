from __future__ import annotations

import json
import socket
import threading
import time
from collections.abc import Iterator
from pathlib import Path

import pytest
import uvicorn
from playwright.sync_api import Browser, Playwright, sync_playwright

from btb_browser.web import create_app


def write_episode(path: Path, episode_id: int, **overrides: object) -> None:
    payload: dict[str, object] = {
        "id": episode_id,
        "title": f"Episode {episode_id}",
        "description": f"Description {episode_id}",
        "startDate": "2026-04-20T00:00:00Z",
        "duration": 3600,
        "imageUrl": "https://example.com/image.jpg",
        "podcastSlug": "behind-the-bastards",
        "transcriptionAvailable": False,
    }
    payload.update(overrides)
    path.write_text(json.dumps(payload), encoding="utf-8")


class _TestServer(uvicorn.Server):
    def install_signal_handlers(self) -> None:
        return


def _find_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        sock.listen(1)
        return int(sock.getsockname()[1])


@pytest.fixture
def smoke_archive_root(tmp_path: Path) -> Path:
    episodes_dir = tmp_path / "episodes"
    transcripts_dir = tmp_path / "transcripts"
    episodes_dir.mkdir()
    transcripts_dir.mkdir()

    long_url = "https://example.com/" + ("unbroken-path-segment-" * 24)
    unbreakable_text = "A" * 720
    description = (
        "<p>Now Jimmy Saville is at the top of the world: he's become a radio and TV star.</p>"
        f"<p>{unbreakable_text}</p>"
        f'<p><a href="{long_url}">{long_url}</a></p>'
    )
    write_episode(
        episodes_dir / "1.json",
        1,
        title="A Long Description Episode",
        description=description,
        startDate="2026-04-21T05:00:00Z",
    )
    write_episode(
        episodes_dir / "2.json",
        2,
        title="Another Episode",
        description=description,
        startDate="2026-04-20T05:00:00Z",
    )
    return tmp_path


@pytest.fixture
def live_server(smoke_archive_root: Path) -> Iterator[str]:
    port = _find_free_port()
    app = create_app(smoke_archive_root)
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = _TestServer(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    deadline = time.time() + 10
    while time.time() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                break
        except OSError:
            time.sleep(0.05)
    else:
        server.should_exit = True
        thread.join(timeout=5)
        raise RuntimeError("Timed out waiting for test server")

    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        thread.join(timeout=5)


@pytest.fixture
def playwright_instance() -> Iterator[Playwright]:
    with sync_playwright() as playwright:
        yield playwright


@pytest.fixture
def webkit_browser(playwright_instance: Playwright) -> Iterator[Browser]:
    browser = playwright_instance.webkit.launch()
    try:
        yield browser
    finally:
        browser.close()


def test_home_page_has_no_horizontal_overflow_in_webkit(
    live_server: str,
    webkit_browser: Browser,
) -> None:
    page = webkit_browser.new_page(viewport={"width": 1280, "height": 900})
    page.goto(f"{live_server}/", wait_until="networkidle")

    metrics = page.evaluate(
        """
        () => {
          const doc = document.documentElement;
          const body = document.body;
          return {
            clientWidth: doc.clientWidth,
            scrollWidth: Math.max(doc.scrollWidth, body.scrollWidth),
            cardRight: document.querySelector('.episode-card')?.getBoundingClientRect().right ?? 0,
            viewportWidth: window.innerWidth,
          };
        }
        """
    )

    assert metrics["scrollWidth"] == metrics["clientWidth"]
    assert metrics["cardRight"] <= metrics["viewportWidth"]


def test_home_page_search_row_fits_on_iphone_sized_webkit_viewport(
    live_server: str,
    webkit_browser: Browser,
) -> None:
    page = webkit_browser.new_page(viewport={"width": 390, "height": 844})
    page.goto(f"{live_server}/", wait_until="networkidle")

    metrics = page.evaluate(
        """
        () => {
          const doc = document.documentElement;
          const body = document.body;
          const input = document.querySelector('input[type="search"]');
          const button = document.querySelector('button[type="submit"]');
          return {
            clientWidth: doc.clientWidth,
            scrollWidth: Math.max(doc.scrollWidth, body.scrollWidth),
            inputRight: input?.getBoundingClientRect().right ?? 0,
            buttonRight: button?.getBoundingClientRect().right ?? 0,
            viewportWidth: window.innerWidth,
          };
        }
        """
    )

    assert metrics["scrollWidth"] == metrics["clientWidth"]
    assert metrics["inputRight"] <= metrics["viewportWidth"]
    assert metrics["buttonRight"] <= metrics["viewportWidth"]
