"""structlog wiring for scripts and ingest jobs.

One call — ``configure_logging()`` — picks the renderer based on
``settings.app_env``:

- **prod**: JSON output, one event per line, with ISO-8601 UTC timestamp,
  level, event name, and any ``.bind()``-injected context. Easy for
  GitHub Actions log scraping and downstream log shippers.
- **dev**: a pretty console renderer with the same shape, so local runs
  stay readable.

The default keys (``timestamp`` / ``level`` / ``event``) are part of the
contract so dashboards and alerting can rely on them. Anything passed via
``log.bind(...)`` or as kwargs to a log call lands alongside.

Call from each script's ``main()``; the runtime configuration is process-
wide so a second call from inside the same process is harmless (it
re-applies the same processor chain).
"""

from __future__ import annotations

from typing import Any

import structlog

from subway_ops.config import settings


def configure_logging(*, force_json: bool | None = None) -> None:
    """Configure structlog for the current process.

    ``force_json`` overrides the env-based default — handy for tests that
    want to lock in one renderer regardless of ``APP_ENV``.
    """
    json_output = (
        force_json
        if force_json is not None
        else (settings.app_env == "prod")
    )

    shared_processors: list[Any] = [
        # Inject standard envelope keys before the renderer sees them so
        # the JSON output always carries `timestamp`, `level`, `event`.
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]

    renderer: Any
    if json_output:
        renderer = structlog.processors.JSONRenderer()
    else:
        renderer = structlog.dev.ConsoleRenderer(colors=False)

    structlog.configure(
        processors=[*shared_processors, renderer],
        wrapper_class=structlog.make_filtering_bound_logger(0),
        cache_logger_on_first_use=True,
    )


def is_json_output() -> bool:
    """Tiny convenience for tests / sanity checks."""
    return settings.app_env == "prod"
