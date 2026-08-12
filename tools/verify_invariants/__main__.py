"""Run every invariant check. Exit 1 if any fails.

uv run python -m tools.verify_invariants
uv run python -m tools.verify_invariants --update   # re-record migrations
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import CHECKS
from .check_migrations_append_only import write_manifest

REPO_ROOT = Path(__file__).resolve().parents[2]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="verify_invariants", description=__doc__)
    parser.add_argument(
        "--update",
        action="store_true",
        help="regenerate the migration checksum manifest, then run the checks",
    )
    parser.add_argument(
        "--root",
        type=Path,
        default=REPO_ROOT,
        help="repository root (default: inferred from this file)",
    )
    args = parser.parse_args(argv)

    if args.update:
        manifest = write_manifest(args.root)
        print(f"rewrote {manifest.relative_to(args.root)}")

    results = [module.check(args.root) for module in CHECKS]

    width = max(len(r.name) for r in results)
    for result in results:
        mark = "PASS" if result.ok else "FAIL"
        print(f"  [{mark}] {result.name.ljust(width)}  {result.detail}")
        for violation in result.violations:
            print(f"         - {violation}")

    passed = sum(1 for r in results if r.ok)
    failed_count = len(results) - passed
    print(f"\n{passed} passed, {failed_count} failed")
    return 1 if failed_count else 0


if __name__ == "__main__":
    sys.exit(main())
