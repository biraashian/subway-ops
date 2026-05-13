"""One-time local OAuth flow for the Gmail readonly scope.

Run once per machine. Opens a browser, asks for consent against the
Gmail account that holds the "UoS" label, and writes the resulting
credentials to ``./token.json`` in the current directory.

After the file exists:

    base64 -w0 token.json > token.b64

then paste the contents of ``token.b64`` into the
``GMAIL_TOKEN_JSON_B64`` GitHub Actions secret. ``token.json``
itself is gitignored and must never be committed.
"""

from __future__ import annotations

import sys
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

from subway_ops.uos.gmail_client import DEFAULT_TOKEN_PATH, SCOPES

DEFAULT_CLIENT_SECRET = Path.home() / ".config" / "subway-ops" / "client_secret.json"


def main(argv: list[str] | None = None) -> int:
    argv = argv if argv is not None else sys.argv[1:]
    client_secret = (
        Path(argv[0]).expanduser() if argv else DEFAULT_CLIENT_SECRET
    )
    out = DEFAULT_TOKEN_PATH

    if not client_secret.exists():
        sys.stderr.write(
            f"client_secret.json not found at {client_secret}.\n"
            "Follow docs/gmail_setup.md to download one.\n"
        )
        return 2

    flow = InstalledAppFlow.from_client_secrets_file(
        str(client_secret), list(SCOPES)
    )
    creds = flow.run_local_server(port=0)
    out.write_text(creds.to_json())
    print(
        f"Saved {out}. Base64-encode and add as GMAIL_TOKEN_JSON_B64:\n"
        f"    base64 -w0 {out} > token.b64"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
