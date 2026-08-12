# subway-ops

<!--
  CI badge: replace OWNER with the GitHub user/org that owns the repo
  once it has a remote. Until then GitHub renders this badge as
  "no status" — harmless.
-->
[![CI](https://github.com/amitoj/subway-ops/actions/workflows/ci.yml/badge.svg)](https://github.com/amitoj/subway-ops/actions/workflows/ci.yml)

Internal operations system for a 15-store Subway franchise: ingests Fresh
Connect (LiveIQ) data, builds analytical marts, surfaces a Streamlit
dashboard, runs reconciliation, and emails a weekly digest.

This README is intentionally short. The system is documented in layers, read
downward from the design authority:

- [`codex/`](codex/README.md) — the design authority. What this business is, the
  business calendar, the data model, the conventions. Specs anchor here.
- [`CLAUDE.md`](CLAUDE.md) — Burst operating law: the seven standing rules every
  session works under.
- [`DECISIONS.md`](DECISIONS.md) — the decision log, including the verbatim
  pre-Burst entries.
- [`workshop/WORKSHOP.md`](workshop/WORKSHOP.md) — the board: what is in flight,
  what needs the founder, what is queued.
- [`bench/BENCH.md`](bench/BENCH.md) — open decisions blocking work.
- [`journal/`](journal/) — per-task system of record.
- [`legacy/`](legacy/README.md) — the retired pre-Burst playbook and tracker.
  Kept for prior art; no longer authoritative.

## The gate

One command decides whether work is done:

```bash
bash scripts/verify.sh T-#### pre-merge
```

Exit 0 or it is not finished. It runs the tests, coverage, `mypy --strict`,
ruff, the seven repo invariants in `tools/verify_invariants/`, a database schema
drift check, the codex consistency suite, and evidence presence.

## Quick start

```bash
uv sync                  # install all dependencies
uv run ruff check .      # lint
uv run mypy src/         # type-check
uv run pytest            # tests
```

## Deployment

The Streamlit dashboard ships from `streamlit_app.py` at the repo root.
Two supported targets:

- **Streamlit Community Cloud** (default, free, public URL with in-app
  auth): see [`docs/deployment_streamlit_cloud.md`](docs/deployment_streamlit_cloud.md).
- **Fly.io** (private URL, ~$5/month): see
  [`docs/deployment_flyio.md`](docs/deployment_flyio.md).

After any `pyproject.toml` change, regenerate the pinned dependency list
the deployment reads:

```bash
uv export --frozen --no-dev --no-emit-project --no-hashes > requirements.txt
```
