from typing import cast

import btb_browser.__main__ as browser_cli


def test_main_runs_uvicorn_with_defaults(monkeypatch):
    calls: dict[str, object] = {}

    def fake_run(app, **kwargs):
        calls["app"] = app
        calls.update(kwargs)

    monkeypatch.setattr(browser_cli.uvicorn, "run", fake_run)

    result = browser_cli.main([])

    assert result == 0
    assert calls["app"] == "btb_browser.web:app"
    assert calls["host"] == "127.0.0.1"
    assert calls["port"] == 8000
    assert calls["reload"] is False
    assert calls["log_level"] == "info"
    log_config = cast(dict[str, object], calls["log_config"])
    loggers = cast(dict[str, object], log_config["loggers"])
    browser_logger = cast(dict[str, object], loggers["btb_browser"])
    assert browser_logger["handlers"] == ["default"]
    assert browser_logger["level"] == "INFO"
    assert browser_logger["propagate"] is False


def test_main_accepts_host_port_and_debug(monkeypatch):
    calls: dict[str, object] = {}

    def fake_run(app, **kwargs):
        calls["app"] = app
        calls.update(kwargs)

    monkeypatch.setattr(browser_cli.uvicorn, "run", fake_run)

    result = browser_cli.main(["--host", "0.0.0.0", "--port", "9000", "--debug"])

    assert result == 0
    assert calls["app"] == "btb_browser.web:app"
    assert calls["host"] == "0.0.0.0"
    assert calls["port"] == 9000
    assert calls["reload"] is True
    assert calls["log_level"] == "debug"
    log_config = cast(dict[str, object], calls["log_config"])
    loggers = cast(dict[str, object], log_config["loggers"])
    browser_logger = cast(dict[str, object], loggers["btb_browser"])
    assert browser_logger["level"] == "DEBUG"
