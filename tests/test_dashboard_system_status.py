"""Tests for the pure helpers inside ``pages/5_system_status.py``.

The page itself is rendered by the Streamlit harness; we don't import
it as a module (the page-script convention runs ``main()`` at import
time). Instead we ``importlib``-load the file so we can call the pure
helpers without spinning Streamlit up.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import pytest


def _load_module() -> Any:
    path = Path(__file__).parent.parent / (
        "src/subway_ops/dashboard/pages/5_system_status.py"
    )
    spec = importlib.util.spec_from_file_location("system_status_under_test", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    # ``main()`` runs at module import. Streamlit's bare-mode warnings
    # are noisy but harmless — no DB calls happen because the user_email
    # session-state key is missing on import.
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def mod() -> Any:
    return _load_module()


def test_format_duration_seconds_minutes_hours(mod: Any) -> None:
    assert mod._format_duration(0) == "0.0s"
    assert mod._format_duration(12.5) == "12.5s"
    assert mod._format_duration(75) == "1m 15s"
    assert mod._format_duration(3661) == "1h 1m"
    assert mod._format_duration(None) == "—"
    assert mod._format_duration("not a number") == "—"


def test_status_chip_carries_inline_background(mod: Any) -> None:
    for status in ("success", "running", "failed"):
        chip = mod._status_chip(status)
        assert "background:" in chip
        assert status in chip


def test_status_chip_unknown_falls_back_to_neutral(mod: Any) -> None:
    chip = mod._status_chip("mystery_status")
    assert "background:" in chip


def test_rerun_url_known_job_returns_workflow_link(
    mod: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/repo")
    url = mod._rerun_url("daily_pull")
    assert url is not None
    assert "owner/repo" in url
    assert "daily_pull.yml" in url
    assert url.startswith("https://github.com/")


def test_rerun_url_unknown_job_is_none(mod: Any) -> None:
    assert mod._rerun_url("not_a_real_job") is None


def test_rerun_url_explicit_none_workflow_is_none(mod: Any) -> None:
    """``backfill`` has no scheduled workflow; the page must return
    ``None`` rather than a misleading dispatch URL."""
    assert mod._rerun_url("backfill") is None


def test_gh_repo_env_var_wins(
    mod: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("GITHUB_REPOSITORY", "from/env")
    assert mod._gh_repo() == "from/env"


def test_gh_repo_fallback_default(
    mod: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    # ``st.secrets`` is unavailable in bare mode; the helper must catch
    # the access error and return the working-directory-derived default
    # rather than crashing.
    repo = mod._gh_repo()
    assert "/" in repo  # owner/repo shape
