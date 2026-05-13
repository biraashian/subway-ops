"""Tests for ``subway_ops.observability.configure_logging``.

Renderer selection follows ``settings.app_env``: ``prod`` → JSON,
anything else → pretty console. The test isolates the global structlog
config by snapshotting and restoring it, so other tests' loggers don't
pick up a sticky renderer choice.
"""

from __future__ import annotations

import io
import json

import pytest
import structlog

from subway_ops import observability
from subway_ops.config import Settings


@pytest.fixture(autouse=True)
def _restore_structlog_config() -> None:
    """structlog.configure mutates a process-global. Reset between tests
    so the rest of the suite isn't perturbed by our renderer swaps."""
    structlog.reset_defaults()
    yield
    structlog.reset_defaults()


def _capture_one_event(force_json: bool | None = None) -> str:
    """Configure logging, emit one event with a known shape, return the
    rendered line as a string."""
    sink = io.StringIO()
    observability.configure_logging(force_json=force_json)
    log = structlog.get_logger("test").bind(component="observability_test")
    structlog.configure(
        processors=structlog.get_config()["processors"],
        wrapper_class=structlog.make_filtering_bound_logger(0),
        logger_factory=structlog.PrintLoggerFactory(file=sink),
        cache_logger_on_first_use=False,
    )
    log = structlog.get_logger("test").bind(component="observability_test")
    log.info("hello", store="4092", rows=7)
    return sink.getvalue().strip()


def test_configure_logging_force_json_emits_one_object_per_line() -> None:
    line = _capture_one_event(force_json=True)
    payload = json.loads(line)
    assert payload["event"] == "hello"
    assert payload["level"] == "info"
    assert payload["component"] == "observability_test"
    assert payload["store"] == "4092"
    assert payload["rows"] == 7
    assert "timestamp" in payload
    # Timestamp must be ISO-8601 with a TZ suffix.
    assert payload["timestamp"].endswith("Z") or "+" in payload["timestamp"]


def test_configure_logging_force_console_is_human_readable() -> None:
    line = _capture_one_event(force_json=False)
    # Plain text, not JSON. Just sanity-check the event key + a bound
    # context value made it through.
    assert "hello" in line
    assert "store" in line and "4092" in line


def test_configure_logging_defaults_to_json_in_prod(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        observability,
        "settings",
        Settings(_env_file=None, app_env="prod"),  # type: ignore[call-arg]
    )
    line = _capture_one_event()
    # JSON output parses cleanly.
    json.loads(line)


def test_configure_logging_defaults_to_console_in_dev(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        observability,
        "settings",
        Settings(_env_file=None, app_env="dev"),  # type: ignore[call-arg]
    )
    line = _capture_one_event()
    with pytest.raises(json.JSONDecodeError):
        json.loads(line)


def test_is_json_output_follows_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        observability,
        "settings",
        Settings(_env_file=None, app_env="prod"),  # type: ignore[call-arg]
    )
    assert observability.is_json_output() is True
    monkeypatch.setattr(
        observability,
        "settings",
        Settings(_env_file=None, app_env="dev"),  # type: ignore[call-arg]
    )
    assert observability.is_json_output() is False


def test_configure_logging_is_idempotent_within_a_process() -> None:
    """Calling configure_logging twice must not error — scripts and the
    Streamlit harness may both invoke it within a single Python process."""
    observability.configure_logging(force_json=True)
    observability.configure_logging(force_json=False)
    # No exception → pass. Sanity: structlog still has a config.
    assert structlog.get_config()["processors"]
