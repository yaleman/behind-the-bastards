from __future__ import annotations

from urllib.parse import urlencode
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from markupsafe import Markup

from btb_browser.data import EpisodeRecord, load_archive, paginate_results, search_records

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ARCHIVE_ROOT = PACKAGE_ROOT


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
    return Markup(value)


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
