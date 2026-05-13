# Deploying to Fly.io

Alternative to Streamlit Cloud when you want a private-by-default URL
(e.g. `subway-ops-<random>.fly.dev` instead of `*.streamlit.app`). Costs
about $5/month on the smallest shared instance — the system is no
longer literally free, but only people you share the URL with can find
the dashboard.

## One-time setup

1. **Install `flyctl`** and log in.

   ```bash
   brew install flyctl   # or: curl -L https://fly.io/install.sh | sh
   fly auth login
   ```

2. **Launch the app from the repo root.**

   ```bash
   fly launch --region sjc --no-deploy
   ```

   Accept the defaults: shared-cpu-1x VM, 256 MB RAM, region `sjc`
   (closest to a West-Coast Supabase pooler). The Dockerfile shipped at
   the repo root is picked up automatically. The `--no-deploy` flag
   gives us a chance to set secrets before the first build.

3. **Set the runtime secrets.**

   ```bash
   fly secrets set \
     DATABASE_URL='postgresql://…sslmode=require' \
     AUTH_COOKIE_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(48))')" \
     APP_ENV=prod
   ```

   The shim reads `AUTH_COOKIE_KEY` from the environment when the
   Streamlit `secrets.toml` file isn't present, so no TOML file ships
   inside the image.

4. **Deploy.**

   ```bash
   fly deploy
   ```

   First build takes ~3 minutes (Python wheels). Subsequent deploys are
   cached and ~30 seconds.

5. **Test.**

   ```bash
   fly open
   ```

   Log in as an owner; verify all four pages render.

6. **Bookmark the URL** and add it as the `DASHBOARD_URL` GitHub
   Actions secret so the Wednesday digest links to it.

## Day-to-day

- **Code changes:** `fly deploy` from a clean working tree.
- **Dependency changes:** regenerate `requirements.txt` then `fly deploy`:

  ```bash
  uv export --frozen --no-dev --no-emit-project --no-hashes > requirements.txt
  fly deploy
  ```

- **Secrets rotation:** `fly secrets set KEY=value` — the app
  auto-restarts.

- **Logs:** `fly logs` tails stdout/stderr; useful for debugging
  Streamlit errors that don't surface in the browser.

## Resource notes

- 256 MB is enough headroom for our 14-store mart sizes plus pandas's
  baseline. If pages start OOM-killing, bump to 512 MB via
  `fly scale memory 512`.
- One instance is enough — Streamlit caches per-process, so two
  replicas would just double the SQL load for no UX benefit.
