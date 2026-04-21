from __future__ import annotations

import re
from html import escape
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlencode, urlparse

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from markupsafe import Markup

from btb_browser.data import EpisodeRecord, load_archive, paginate_results, search_records

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ARCHIVE_ROOT = PACKAGE_ROOT
ALLOWED_DESCRIPTION_TAGS = {
    "a",
    "b",
    "blockquote",
    "br",
    "code",
    "em",
    "i",
    "li",
    "ol",
    "p",
    "strong",
    "ul",
}
VOID_DESCRIPTION_TAGS = {"br"}


class _DescriptionHtmlRenderer(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self._parts: list[str] = []
        self._open_tags: list[str] = []

    def render(self, value: str) -> str:
        self.feed(value)
        self.close()
        while self._open_tags:
            self._parts.append(f"</{self._open_tags.pop()}>")
        rendered = "".join(self._parts)
        return re.sub(r"<li>\s*</li>", "", rendered)

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag not in ALLOWED_DESCRIPTION_TAGS:
            return
        rendered_attrs = self._render_attrs(tag, attrs)
        if tag == "a" and not rendered_attrs:
            return
        self._parts.append(f"<{tag}{rendered_attrs}>")
        if tag not in VOID_DESCRIPTION_TAGS:
            self._open_tags.append(tag)

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag not in ALLOWED_DESCRIPTION_TAGS:
            return
        rendered_attrs = self._render_attrs(tag, attrs)
        if tag == "a" and not rendered_attrs:
            return
        self._parts.append(f"<{tag}{rendered_attrs}>")
        if tag in VOID_DESCRIPTION_TAGS:
            self._parts[-1] = f"<{tag}{rendered_attrs}>"
        else:
            self._parts.append(f"</{tag}>")

    def handle_endtag(self, tag: str) -> None:
        if tag not in ALLOWED_DESCRIPTION_TAGS or tag in VOID_DESCRIPTION_TAGS:
            return
        for index in range(len(self._open_tags) - 1, -1, -1):
            if self._open_tags[index] != tag:
                continue
            for closing_tag in reversed(self._open_tags[index:]):
                self._parts.append(f"</{closing_tag}>")
            del self._open_tags[index:]
            return

    def handle_data(self, data: str) -> None:
        self._parts.append(escape(data))

    def handle_entityref(self, name: str) -> None:
        self._parts.append(f"&{name};")

    def handle_charref(self, name: str) -> None:
        self._parts.append(f"&#{name};")

    def handle_comment(self, data: str) -> None:
        return

    def _render_attrs(self, tag: str, attrs: list[tuple[str, str | None]]) -> str:
        if tag != "a":
            return ""
        for key, value in attrs:
            if key != "href" or not value:
                continue
            if not self._is_safe_href(value):
                continue
            escaped_value = escape(value, quote=True)
            return f' href="{escaped_value}" rel="noopener noreferrer" target="_blank"'
        return ""

    @staticmethod
    def _is_safe_href(value: str) -> bool:
        parsed = urlparse(value)
        return parsed.scheme in {"http", "https"}


def _find_episode(records: list[EpisodeRecord], episode_id: int) -> EpisodeRecord | None:
    for record in records:
        if record.id == episode_id:
            return record
    return None


def _format_duration(seconds: int | None) -> str:
    if seconds is None:
        return ""
    total_seconds = max(int(seconds), 0)
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


def _excerpt_text(text: str, limit: int = 120) -> str:
    compact = " ".join(text.split())
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1].rstrip() + "…"


def _page_url(request: Request, *, page: int, query: str) -> str:
    params: dict[str, str | int] = {"page": page}
    if query:
        params["q"] = query
    return f"{request.url.path}?{urlencode(params)}"


def _render_description_html(value: object) -> Markup:
    if not isinstance(value, str):
        return Markup("")
    return Markup(_DescriptionHtmlRenderer().render(value))


def create_app(
    archive_root: Path | str = DEFAULT_ARCHIVE_ROOT,
    *,
    episodes_dir: Path | None = None,
    transcripts_dir: Path | None = None,
) -> FastAPI:
    root = Path(archive_root)
    resolved_episodes_dir = episodes_dir or root / "episodes"
    resolved_transcripts_dir = transcripts_dir or root / "transcripts"
    records = load_archive(resolved_episodes_dir, resolved_transcripts_dir)

    app = FastAPI()
    templates = Jinja2Templates(directory=str(PACKAGE_ROOT / "templates"))
    static_dir = PACKAGE_ROOT / "static"
    if static_dir.exists():
        app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

    @app.get("/", response_class=HTMLResponse)
    def index(request: Request, q: str = "", page: int = 1) -> HTMLResponse:
        filtered_records = search_records(records, q) if q else list(records)
        page_records, total_pages = paginate_results(filtered_records, page=page, page_size=24)
        effective_page = max(1, min(page, total_pages))
        has_previous = effective_page > 1
        has_next = effective_page < total_pages
        return templates.TemplateResponse(
            request,
            "index.html",
            {
                "query": q,
                "records": page_records,
                "total_records": len(filtered_records),
                "page": effective_page,
                "total_pages": total_pages,
                "has_previous": has_previous,
                "has_next": has_next,
                "previous_page_url": _page_url(request, page=effective_page - 1, query=q) if has_previous else "",
                "next_page_url": _page_url(request, page=effective_page + 1, query=q) if has_next else "",
                "format_duration": _format_duration,
                "render_description_html": _render_description_html,
            },
        )

    @app.get("/episodes/{episode_id}", response_class=HTMLResponse)
    def detail(request: Request, episode_id: int) -> HTMLResponse:
        record = _find_episode(records, episode_id)
        if record is None:
            raise HTTPException(status_code=404, detail="Episode not found")
        return templates.TemplateResponse(
            request,
            "detail.html",
            {
                "record": record,
                "format_duration": _format_duration,
                "render_description_html": _render_description_html,
            },
        )

    return app


app = create_app()
