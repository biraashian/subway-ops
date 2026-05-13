# subway-ops

Internal operations system for a 15-store Subway franchise: ingests Fresh
Connect (LiveIQ) data, builds analytical marts, surfaces a Streamlit
dashboard, runs reconciliation, and emails a weekly digest.

This README is intentionally short. The full build is documented in:

- [`SUBWAY_OPS_BUILD_PLAYBOOK.md`](SUBWAY_OPS_BUILD_PLAYBOOK.md) — task-by-task
  prompts, acceptance criteria, and verification commands.
- [`SUBWAY_OPS_TASKS.md`](SUBWAY_OPS_TASKS.md) — working checklist.
- [`CLAUDE.md`](CLAUDE.md) — conventions every Claude Code session reads.
- [`decisions.md`](decisions.md) — architectural decision log.

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
