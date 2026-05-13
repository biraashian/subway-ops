# Deploying to Streamlit Community Cloud

This is the default path for the dashboard. Free, public URL, in-app auth
(see `subway_ops.dashboard.auth`) gates everything sensitive.

## One-time setup

1. **Sign in to Streamlit Community Cloud.**
   Go to <https://share.streamlit.io>, pick "Continue with GitHub",
   authorise the Streamlit app on the `subway-ops` repo.

2. **Create the app.**
   - **Repository:** your `subway-ops` repo (private is fine).
   - **Branch:** `main`.
   - **Main file path:** `streamlit_app.py`.
   - Click *Advanced settings* and set the Python version to **3.12**.

3. **Paste secrets.**
   In the app's Settings → Secrets pane, paste the same TOML structure
   you keep locally in `.streamlit/secrets.toml`. **Never commit that
   file** — it's `.gitignore`'d.

   Minimum required:

   ```toml
   database_url = "postgresql://…@aws-1-us-west-1.pooler.supabase.com:5432/postgres?sslmode=require"
   auth_cookie_key = "<random 32+ char string>"
   ```

   Generate the cookie key once with `python -c "import secrets; print(secrets.token_urlsafe(48))"`
   and reuse it across redeploys — rotating it logs everyone out.

4. **Visibility.**
   Set the app to **Public**. In-app auth gates every page; making the
   URL itself private requires inviting each Streamlit user individually,
   which gets noisy for five operators. Public + login is the cleaner
   posture.

5. **Wait for the first build.**
   First deploy installs from `requirements.txt` and can take 3-5
   minutes. Subsequent redeploys ride the cache.

6. **Bookmark the URL.**
   Add the URL as the `DASHBOARD_URL` secret in GitHub Actions so the
   Wednesday digest can link to it.

## Day-to-day

- **Code changes:** push to `main`. Streamlit Cloud auto-redeploys on
  each push, usually within 60 seconds.
- **Dependency changes:** after editing `pyproject.toml`, regenerate
  the requirements lock:

  ```bash
  uv export --frozen --no-dev --no-emit-project --no-hashes > requirements.txt
  git add requirements.txt && git commit -m "deps: regenerate requirements.txt"
  ```

  Streamlit Cloud will pick up the new file on the next push.

- **Secrets rotation:** edit them in the Settings UI and click "Reboot
  app". No redeploy needed.

## Smoke check after a deploy

1. Open the dashboard URL.
2. Log in as a known user (owner first to test full visibility).
3. Confirm the four pages render and the sidebar shows "Last data
   refresh: <recent timestamp>".
4. Log in as a field manager next; confirm filtered stores.

If any of the above fails, the first place to look is the app's "Manage
app" → "Logs" pane — Streamlit captures stdout/stderr there.
