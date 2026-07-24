from __future__ import annotations

import os
import sys
import types
import unittest
from unittest.mock import patch


class FakeRequest:
    pass


class FakeCredentials:
    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.scopes = kwargs["scopes"]
        self.refresh_called = False

    def refresh(self, request):
        self.refresh_called = isinstance(request, FakeRequest)


def _install_google_auth_stubs() -> None:
    google = types.ModuleType("google")
    google_oauth2 = types.ModuleType("google.oauth2")
    google_oauth2_credentials = types.ModuleType("google.oauth2.credentials")
    google_auth = types.ModuleType("google.auth")
    google_auth_transport = types.ModuleType("google.auth.transport")
    google_auth_requests = types.ModuleType("google.auth.transport.requests")

    google_oauth2_credentials.Credentials = FakeCredentials
    google_auth_requests.Request = FakeRequest

    sys.modules.setdefault("google", google)
    sys.modules.setdefault("google.oauth2", google_oauth2)
    sys.modules.setdefault("google.oauth2.credentials", google_oauth2_credentials)
    sys.modules.setdefault("google.auth", google_auth)
    sys.modules.setdefault("google.auth.transport", google_auth_transport)
    sys.modules.setdefault("google.auth.transport.requests", google_auth_requests)


def _install_token_generator_stubs() -> None:
    google_auth_oauthlib = types.ModuleType("google_auth_oauthlib")
    google_auth_oauthlib_flow = types.ModuleType("google_auth_oauthlib.flow")

    class FakeInstalledAppFlow:
        @classmethod
        def from_client_config(cls, client_config, scopes):
            instance = cls()
            instance.client_config = client_config
            instance.scopes = scopes
            return instance

    google_auth_oauthlib_flow.InstalledAppFlow = FakeInstalledAppFlow
    sys.modules.setdefault("google_auth_oauthlib", google_auth_oauthlib)
    sys.modules.setdefault("google_auth_oauthlib.flow", google_auth_oauthlib_flow)


_install_google_auth_stubs()
_install_token_generator_stubs()

from src import google_auth
from src.config import Config
import generate_tokens


class GoogleOAuthSplitTests(unittest.TestCase):
    def test_workspace_credentials_contain_workspace_scopes_only(self) -> None:
        with (
            patch.object(google_auth, "Credentials", FakeCredentials),
            patch.object(google_auth, "Request", FakeRequest),
        ):
            credentials = google_auth.build_google_credentials(
                "client-id",
                "client-secret",
                "workspace-refresh",
                google_auth.WORKSPACE_SCOPES,
            )

        self.assertEqual(credentials.scopes, google_auth.WORKSPACE_SCOPES)
        self.assertNotIn("https://www.googleapis.com/auth/youtube.upload", credentials.scopes)
        self.assertTrue(credentials.refresh_called)

    def test_youtube_credentials_contain_youtube_scope_only(self) -> None:
        with (
            patch.object(google_auth, "Credentials", FakeCredentials),
            patch.object(google_auth, "Request", FakeRequest),
        ):
            credentials = google_auth.build_google_credentials(
                "client-id",
                "client-secret",
                "youtube-refresh",
                google_auth.YOUTUBE_SCOPES,
            )

        self.assertEqual(credentials.scopes, google_auth.YOUTUBE_SCOPES)
        self.assertNotIn("https://www.googleapis.com/auth/drive.readonly", credentials.scopes)
        self.assertNotIn("https://www.googleapis.com/auth/drive.file", credentials.scopes)
        self.assertNotIn("https://www.googleapis.com/auth/spreadsheets", credentials.scopes)

    def test_workspace_scopes_never_include_youtube_upload(self) -> None:
        self.assertNotIn("https://www.googleapis.com/auth/youtube.upload", google_auth.WORKSPACE_SCOPES)

    def test_youtube_scopes_never_include_drive_or_sheets(self) -> None:
        self.assertEqual(google_auth.YOUTUBE_SCOPES, ["https://www.googleapis.com/auth/youtube.upload"])

    def test_missing_workspace_refresh_token_fails_clearly(self) -> None:
        env = self._required_env()
        env.pop("GOOGLE_WORKSPACE_REFRESH_TOKEN")
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaisesRegex(RuntimeError, "GOOGLE_WORKSPACE_REFRESH_TOKEN"):
                Config.from_env()

    def test_missing_youtube_refresh_token_fails_clearly(self) -> None:
        env = self._required_env()
        env.pop("GOOGLE_YOUTUBE_REFRESH_TOKEN")
        with patch.dict(os.environ, env, clear=True):
            with self.assertRaisesRegex(RuntimeError, "GOOGLE_YOUTUBE_REFRESH_TOKEN"):
                Config.from_env()

    def test_token_generator_selects_workspace_scopes(self) -> None:
        with patch("builtins.input", return_value="1"):
            label, secret_name, scopes = generate_tokens.choose_token_type()

        self.assertEqual(label, "Workspace (Drive + Sheets)")
        self.assertEqual(secret_name, "GOOGLE_WORKSPACE_REFRESH_TOKEN")
        self.assertEqual(scopes, google_auth.WORKSPACE_SCOPES)
        self.assertNotIn("https://www.googleapis.com/auth/youtube.upload", scopes)

    def test_token_generator_selects_youtube_scopes(self) -> None:
        with patch("builtins.input", return_value="2"):
            label, secret_name, scopes = generate_tokens.choose_token_type()

        self.assertEqual(label, "YouTube")
        self.assertEqual(secret_name, "GOOGLE_YOUTUBE_REFRESH_TOKEN")
        self.assertEqual(scopes, google_auth.YOUTUBE_SCOPES)
        self.assertNotIn("https://www.googleapis.com/auth/drive.file", scopes)

    @staticmethod
    def _required_env() -> dict[str, str]:
        return {
            "GOOGLE_CLIENT_ID": "client-id",
            "GOOGLE_CLIENT_SECRET": "client-secret",
            "GOOGLE_WORKSPACE_REFRESH_TOKEN": "workspace-refresh",
            "GOOGLE_YOUTUBE_REFRESH_TOKEN": "youtube-refresh",
            "GOOGLE_DRIVE_FOLDER_ID": "drive-folder",
            "GOOGLE_SHEET_ID": "sheet",
            "IG_ACCESS_TOKEN": "ig-token",
            "IG_BUSINESS_ACCOUNT_ID": "ig-business-id",
        }


if __name__ == "__main__":
    unittest.main()
