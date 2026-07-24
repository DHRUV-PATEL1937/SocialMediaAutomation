from __future__ import annotations

import json
import os

from google_auth_oauthlib.flow import InstalledAppFlow

from src.google_auth import WORKSPACE_SCOPES, YOUTUBE_SCOPES


TOKEN_OPTIONS = {
    "1": ("Workspace (Drive + Sheets)", "GOOGLE_WORKSPACE_REFRESH_TOKEN", WORKSPACE_SCOPES),
    "2": ("YouTube", "GOOGLE_YOUTUBE_REFRESH_TOKEN", YOUTUBE_SCOPES),
}


def main() -> None:
    client_id = os.getenv("GOOGLE_CLIENT_ID") or input("Google OAuth client ID: ").strip()
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET") or input("Google OAuth client secret: ").strip()
    label, secret_name, scopes = choose_token_type()

    client_config = {
        "installed": {
            "client_id": client_id,
            "client_secret": client_secret,
            "auth_uri": "https://accounts.google.com/o/oauth2/auth",
            "token_uri": "https://oauth2.googleapis.com/token",
            "redirect_uris": ["http://localhost"],
        }
    }

    print(f"\nGenerating {label} refresh token.")
    print("Requested scopes:")
    print(json.dumps(scopes, indent=2))

    flow = InstalledAppFlow.from_client_config(client_config, scopes)
    credentials = flow.run_local_server(port=0, prompt="consent", access_type="offline")

    print(f"\nSave this value as the {secret_name} GitHub secret:\n")
    print(credentials.refresh_token)
    print("\nScopes granted:")
    print(json.dumps(credentials.scopes, indent=2))


def choose_token_type() -> tuple[str, str, list[str]]:
    print("Which Google refresh token do you want to generate?")
    print("1. Workspace (Drive + Sheets)")
    print("2. YouTube")
    choice = input("Enter 1 or 2: ").strip()
    if choice not in TOKEN_OPTIONS:
        raise RuntimeError("Invalid selection. Enter 1 for Workspace or 2 for YouTube.")
    return TOKEN_OPTIONS[choice]


if __name__ == "__main__":
    main()
