from __future__ import annotations

import argparse
from copy import deepcopy
from collections.abc import Sequence

import uvicorn
from uvicorn.config import LOGGING_CONFIG

APP_IMPORT_PATH = "btb_browser.web:app"


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="behind-the-bastards")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--debug", action="store_true")
    return parser


def _build_log_config(log_level: str) -> dict[str, object]:
    log_config = deepcopy(LOGGING_CONFIG)
    loggers = log_config.setdefault("loggers", {})
    assert isinstance(loggers, dict)
    loggers["btb_browser"] = {
        "handlers": ["default"],
        "level": log_level.upper(),
        "propagate": False,
    }
    return log_config


def main(argv: Sequence[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    log_level = "debug" if args.debug else "info"
    uvicorn.run(
        APP_IMPORT_PATH,
        host=args.host,
        port=args.port,
        reload=args.debug,
        log_level=log_level,
        log_config=_build_log_config(log_level),
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
