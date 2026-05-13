"""CLI wrapper around `subway_ops.db.migrate.apply_migrations`.

    uv run python scripts/migrate.py
"""

from __future__ import annotations

import sys

from subway_ops.db.migrate import apply_migrations, discover_migrations
from subway_ops.observability import configure_logging


def main() -> int:
    configure_logging()
    newly_applied = apply_migrations()
    total = len(discover_migrations())
    skipped = total - len(newly_applied)
    print(f"Applied {len(newly_applied)} migrations, skipped {skipped}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
