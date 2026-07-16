from __future__ import annotations

from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request


SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/youtube.upload",
]


def build_google_credentials(client_id: str, client_secret: str, refresh_token: str) -> Credentials:
    credentials = Credentials(
        token=None,
        refresh_token=refresh_token,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=client_id,
        client_secret=client_secret,
        scopes=SCOPES,
    )
    credentials.refresh(Request())
    return credentials
