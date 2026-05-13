# Gmail API setup (one-time, manual)

The University of Subway pipeline (Phase 6) reads compliance emails
out of Gmail with read-only OAuth. This doc walks through the
five-minute setup. Re-do it only if the OAuth client is deleted or
the Gmail account changes.

## Prerequisites

- A Gmail account that already filters uOS emails into a `UoS` label.
  Set up that filter first: **Settings → Filters and Blocked Addresses
  → Create a new filter**, `From: noreply@universityofsubway.com`
  (or whatever the actual sender is), apply label `UoS`, don't
  archive.
- Python 3.12 + this repo cloned locally, with `uv sync` done.
- About 5 minutes.

## 1. Create a Google Cloud project

1. Go to [console.cloud.google.com](https://console.cloud.google.com).
2. Top-left project picker → **New Project**. Name it `subway-ops`
   (or anything — it's never user-facing).
3. Wait for the project to provision; switch to it.

## 2. Enable the Gmail API

1. **APIs & Services → Library**.
2. Search for **Gmail API**.
3. **Enable**.

## 3. Configure the OAuth consent screen

1. **APIs & Services → OAuth consent screen**.
2. User type: **External** (you're using a regular Gmail account,
   not a Workspace one). **Create**.
3. Fill in app name (`subway-ops`), user support email (yours),
   developer email (yours). Save and continue.
4. Scopes: click **Add or remove scopes**, find
   `https://www.googleapis.com/auth/gmail.readonly`, add it. Save.
5. Test users: add the Gmail account you'll be reading from. Save.

Leave the app in **Testing** mode. Tokens issued in Testing mode are
valid forever as long as the test-user list still contains your
address.

## 4. Create the OAuth client

1. **APIs & Services → Credentials → Create credentials → OAuth client ID**.
2. Application type: **Desktop application**. Name: `subway-ops local`.
3. **Create**. Download the JSON.
4. Move the downloaded file to:

   ```bash
   mkdir -p ~/.config/subway-ops
   mv ~/Downloads/client_secret*.json ~/.config/subway-ops/client_secret.json
   ```

   `client_secret*.json` is gitignored — never commit it.

## 5. Run the OAuth flow once

From the repo root:

```bash
uv run python scripts/gmail_get_token.py
```

A browser tab opens. Sign into the test-user Gmail account.
Approve the read-only Gmail scope. The script writes
`./token.json` and prints:

```
Saved token.json. Base64-encode and add as GMAIL_TOKEN_JSON_B64:
    base64 -w0 token.json > token.b64
```

`token.json` is gitignored alongside `client_secret*.json`.

## 6. Wire the token into GitHub Actions

Run the printed command:

```bash
base64 -w0 token.json > token.b64
```

(On macOS the `base64` binary doesn't accept `-w0`; use
`base64 -i token.json -o token.b64` instead — it produces a single-
line file natively.)

Copy the contents of `token.b64` and paste it into a new
**Repository secret** in GitHub → Settings → Secrets and variables →
Actions:

- **Name:** `GMAIL_TOKEN_JSON_B64`
- **Value:** (paste)

The Phase 6 ingest workflow reads this secret. Local tests do not —
they monkey-patch the client.

## 7. Verify

```bash
uv run pytest tests/test_gmail_client.py
```

A quick smoke test from a Python REPL (optional):

```bash
uv run python -c "
from subway_ops.uos.gmail_client import GmailClient
gc = GmailClient()
hits = gc.search('label:UoS newer_than:30d', max_results=5)
print(f'{len(hits)} hits')
for h in hits:
    print(' ', h.id)
"
```

If that prints message IDs, you're done.

## Rotating credentials

If you ever revoke access from the Google account, repeat steps 5–6
to get a fresh `token.json` + new `GMAIL_TOKEN_JSON_B64` secret. The
client never writes back to the secret store — refreshes happen in
memory per CI run.
