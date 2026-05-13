"""Pull recent uOS compliance emails and stage them.

Cron-driven entrypoint that wraps ``subway_ops.uos.ingest.ingest_recent``.
A separate workflow from ``daily_pull`` because the Gmail OAuth token
needs occasional human intervention (re-consent if revoked) and we
don't want that to block the daily FreshConnect ingest.

Default lookback: 7 days, which more than covers a weekly digest
cadence plus an occasional run-skip without re-pulling history.
``--days`` overrides for one-off backfills.
"""

from __future__ import annotations

import argparse
import sys

import structlog

from subway_ops.observability import configure_logging
from subway_ops.uos.ingest import DEFAULT_DAYS, ingest_recent

log = structlog.get_logger(__name__)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--days",
        type=int,
        default=DEFAULT_DAYS,
        help=f"Gmail lookback window (default: {DEFAULT_DAYS}).",
    )
    args = parser.parse_args(argv)

    configure_logging()

    result = ingest_recent(days=args.days)
    print(
        f"uOS pull: {result.messages_new} new messages "
        f"({result.messages_seen} seen), {result.rows_written} compliance "
        f"rows written, {result.rows_skipped_unknown_store} skipped "
        f"(unknown store), {len(result.unparsed_rows)} unparsed rows."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
