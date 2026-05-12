"""Seed reference tables (field managers, stores, users) from CSVs.

Reads:
    seed/field_managers.csv  -> ref_field_managers
    seed/stores.csv          -> ref_stores  (FM assignment derived from field_managers.csv)
    seed/users.csv           -> ref_users   (prompts for password, bcrypt-hashed)

Idempotent: re-runs upsert and leave existing user passwords alone.

CLI:
    uv run python scripts/seed_reference.py
    uv run python scripts/seed_reference.py --reset-password user@example.com
    uv run python scripts/seed_reference.py --no-users    # skip user seeding

Migrations: this script delegates to `scripts/migrate.py`, which records
applied migrations in `ops_migrations` with a SHA-256 checksum.
"""

from __future__ import annotations

import argparse
import csv
import getpass
import os
import sys
from collections.abc import Iterable
from datetime import date
from pathlib import Path

import bcrypt
import psycopg
import structlog
from dateutil import parser as dateparser
from dotenv import load_dotenv

from subway_ops.db.migrate import apply_migrations as _runner_apply_migrations

REPO_ROOT = Path(__file__).resolve().parent.parent
SEED_DIR = REPO_ROOT / "seed"

TIMEZONE_ALIASES = {
    "PST": "America/Los_Angeles",
    "PDT": "America/Los_Angeles",
    "PT": "America/Los_Angeles",
}

log = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Connection helper
# ---------------------------------------------------------------------------


def get_database_url() -> str:
    load_dotenv(REPO_ROOT / ".env")
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL not set. Add it to .env or export it.")
    return url


def connect() -> psycopg.Connection:
    return psycopg.connect(get_database_url())


# ---------------------------------------------------------------------------
# Migration runner — delegates to scripts/migrate.py
# ---------------------------------------------------------------------------


def apply_migrations(conn: psycopg.Connection | None = None) -> list[str]:
    """Apply any pending migrations via the canonical runner.

    The `conn` argument is accepted (and ignored) for backward compatibility
    with callers that already hold a psycopg connection: the runner opens its
    own SQLAlchemy engine from `DATABASE_URL`.

    Returns the list of filenames newly applied this run.
    """
    del conn  # accepted for compatibility; runner uses its own engine
    return _runner_apply_migrations()


# ---------------------------------------------------------------------------
# CSV loaders
# ---------------------------------------------------------------------------


def _split_csv_list(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


def load_field_managers() -> list[dict[str, str | list[str]]]:
    """Parse seed/field_managers.csv into structured rows."""
    path = SEED_DIR / "field_managers.csv"
    rows: list[dict[str, str | list[str]]] = []
    with path.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            role_raw = (r.get("role") or "").strip().lower()
            role = "operations_manager" if "operations" in role_raw else "field_manager"
            rows.append(
                {
                    "name": (r["field_manager_name"] or "").strip(),
                    "email": (r["email"] or "").strip(),
                    "store_numbers": _split_csv_list(r.get("store_numbers_csv") or ""),
                    "role": role,
                }
            )
    return rows


def load_stores() -> list[dict[str, str | None]]:
    """Parse seed/stores.csv into structured rows."""
    path = SEED_DIR / "stores.csv"
    rows: list[dict[str, str | None]] = []
    with path.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            tz_raw = (r.get("timezone") or "").strip()
            tz = TIMEZONE_ALIASES.get(tz_raw.upper(), tz_raw or "America/Los_Angeles")
            rows.append(
                {
                    "store_number": (r["store_number"] or "").strip(),
                    "store_name": (r["store_name"] or "").strip(),
                    "city": (r["city"] or "").strip(),
                    "state": (r["state"] or "").strip().upper(),
                    "timezone": tz,
                    "store_manager_name": (r.get("field_manager_name") or "").strip() or None,
                    "opening_date_raw": (r.get("opening_date_estimate") or "").strip(),
                }
            )
    return rows


def load_users() -> list[dict[str, str | list[str] | None]]:
    """Parse seed/users.csv into structured rows."""
    path = SEED_DIR / "users.csv"
    rows: list[dict[str, str | list[str] | None]] = []
    with path.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            stores = _split_csv_list(r.get("assigned_stores_csv") or "")
            rows.append(
                {
                    "email": (r["email"] or "").strip().lower(),
                    "display_name": (r["display_name"] or "").strip(),
                    "role": (r["role"] or "").strip(),
                    "assigned_stores": stores if stores else None,
                }
            )
    return rows


def _parse_opening_date(raw: str) -> date | None:
    if not raw:
        return None
    try:
        return dateparser.parse(raw, fuzzy=False).date()
    except (ValueError, TypeError):
        log.warning("opening_date_unparseable", raw=raw)
        return None


# ---------------------------------------------------------------------------
# Upserts
# ---------------------------------------------------------------------------


def seed_field_managers(conn: psycopg.Connection) -> int:
    fms = load_field_managers()
    with conn.cursor() as cur:
        for fm in fms:
            cur.execute(
                """
                INSERT INTO ref_field_managers (name, email, is_active)
                VALUES (%s, %s, true)
                ON CONFLICT (name) DO UPDATE SET
                    email = EXCLUDED.email
                """,
                (fm["name"], fm["email"]),
            )
    conn.commit()
    return len(fms)


def seed_stores(conn: psycopg.Connection) -> int:
    fms = load_field_managers()
    stores = load_stores()

    valid_store_numbers = {s["store_number"] for s in stores}
    store_to_fm: dict[str, str] = {}
    for fm in fms:
        name = fm["name"]
        assert isinstance(name, str)
        store_numbers = fm["store_numbers"]
        assert isinstance(store_numbers, list)
        for sn in store_numbers:
            if sn not in valid_store_numbers:
                log.warning(
                    "fm_references_unknown_store",
                    field_manager=name,
                    store_number=sn,
                )
                continue
            store_to_fm[sn] = name

    with conn.cursor() as cur:
        for s in stores:
            store_number = s["store_number"]
            assert isinstance(store_number, str)
            fm_name = store_to_fm.get(store_number)
            opening_date = _parse_opening_date(s["opening_date_raw"] or "")
            cur.execute(
                """
                INSERT INTO ref_stores (
                    store_number, store_name, city, state, timezone,
                    field_manager_name, store_manager_name, opening_date, is_active
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, true)
                ON CONFLICT (store_number) DO UPDATE SET
                    store_name         = EXCLUDED.store_name,
                    city               = EXCLUDED.city,
                    state              = EXCLUDED.state,
                    timezone           = EXCLUDED.timezone,
                    field_manager_name = EXCLUDED.field_manager_name,
                    store_manager_name = EXCLUDED.store_manager_name,
                    opening_date       = EXCLUDED.opening_date,
                    updated_at         = now()
                """,
                (
                    store_number,
                    s["store_name"],
                    s["city"],
                    s["state"],
                    s["timezone"],
                    fm_name,
                    s["store_manager_name"],
                    opening_date,
                ),
            )
    conn.commit()
    return len(stores)


def _hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def _existing_user_emails(conn: psycopg.Connection) -> set[str]:
    with conn.cursor() as cur:
        cur.execute("SELECT email FROM ref_users")
        return {row[0] for row in cur.fetchall()}


def _prompt_password(email: str) -> str:
    while True:
        p1 = getpass.getpass(f"Password for {email}: ")
        if len(p1) < 12:
            sys.stderr.write("Password must be at least 12 characters.\n")
            continue
        p2 = getpass.getpass("Confirm: ")
        if p1 != p2:
            sys.stderr.write("Mismatch. Try again.\n")
            continue
        return p1


def seed_users(
    conn: psycopg.Connection,
    *,
    reset_emails: Iterable[str] = (),
) -> int:
    users = load_users()
    existing = _existing_user_emails(conn)
    reset_set = {e.lower() for e in reset_emails}

    seeded = 0
    with conn.cursor() as cur:
        for u in users:
            email = u["email"]
            assert isinstance(email, str)
            display = u["display_name"]
            role = u["role"]
            assigned = u["assigned_stores"]

            if email in existing and email not in reset_set:
                continue

            password = _prompt_password(email)
            password_hash = _hash_password(password)

            cur.execute(
                """
                INSERT INTO ref_users (
                    email, display_name, role, password_hash, assigned_stores, is_active
                ) VALUES (%s, %s, %s, %s, %s, true)
                ON CONFLICT (email) DO UPDATE SET
                    display_name    = EXCLUDED.display_name,
                    role            = EXCLUDED.role,
                    password_hash   = EXCLUDED.password_hash,
                    assigned_stores = EXCLUDED.assigned_stores
                """,
                (email, display, role, password_hash, assigned),
            )
            seeded += 1
    conn.commit()
    return seeded


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--reset-password",
        action="append",
        default=[],
        metavar="EMAIL",
        help="Re-prompt for a user's password (repeatable).",
    )
    p.add_argument(
        "--no-users",
        action="store_true",
        help="Skip the interactive user-seeding step (FMs and stores only).",
    )
    return p


def main(argv: list[str] | None = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    structlog.configure(processors=[structlog.dev.ConsoleRenderer()])

    with connect() as conn:
        newly_applied = apply_migrations(conn)
        if newly_applied:
            log.info("migrations_applied", count=len(newly_applied), files=newly_applied)
        else:
            log.info("migrations_up_to_date")

        n_fm = seed_field_managers(conn)
        log.info("field_managers_seeded", count=n_fm)

        n_store = seed_stores(conn)
        log.info("stores_seeded", count=n_store)

        if args.no_users:
            log.info("users_skipped")
        else:
            n_user = seed_users(conn, reset_emails=args.reset_password)
            log.info("users_seeded_or_updated", count=n_user)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
