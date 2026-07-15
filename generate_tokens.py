from __future__ import annotations

import json
import os

from google_auth_oauthlib.flow import InstalledAppFlow

from src.google_auth import SCOPES


def main() -> None:
    client_id = os.getenv("GOOGLE_CLIENT_ID") or input("Google OAuth client ID: ").strip()
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET") or input("Google OAuth client secret: ").strip()

    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }

    flow = InstalledAppFlow.from_client_config(client_config, SCOPES)
    credentials = flow.run_local_server(port=0, prompt="consent", access_type="offline")

    print("\nSave this value as the GOOGLE_REFRESH_TOKEN GitHub secret:\n")
    print(credentials.refresh_token)
    print("\nScopes granted:")
    print(json.dumps(credentials.scopes, indent=2))


if __name__ == "__main__":
    main()
