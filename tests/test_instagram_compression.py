from __future__ import annotations

import sys
import tempfile
import types
import unittest
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import Mock, patch

from src import video_compressor
from src.video_compressor import (
    BYTES_PER_MB,
    INSTAGRAM_TEMP_FILE_LIMIT_BYTES,
    InstagramCompressionError,
    VideoMetadata,
)


def _sized_file(path: Path, size_mb: int) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        handle.truncate(size_mb * BYTES_PER_MB)
    return path


class InstagramCompressorTests(unittest.TestCase):
    def test_140_mb_input_compresses_below_target(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = _sized_file(Path(temp_dir) / "input.mp4", 140)

            def fake_ffmpeg(**kwargs):
                _sized_file(kwargs["output_path"], 49)
                return 12.0

            with (
                patch.object(video_compressor.shutil, "which", side_effect=lambda name: name),
                patch.object(video_compressor, "probe_video_metadata", return_value=VideoMetadata(142.5, 1080, 1920)),
                patch.object(video_compressor, "run_ffmpeg", side_effect=fake_ffmpeg),
            ):
                output_path = video_compressor.compress_for_instagram(input_path)

            self.assertLessEqual(output_path.stat().st_size, 50 * BYTES_PER_MB)

    def test_446_mb_input_compresses_below_limit(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = _sized_file(Path(temp_dir) / "input.mp4", 446)

            def fake_ffmpeg(**kwargs):
                _sized_file(kwargs["output_path"], 50)
                return 25.0

            with (
                patch.object(video_compressor.shutil, "which", side_effect=lambda name: name),
                patch.object(video_compressor, "probe_video_metadata", return_value=VideoMetadata(142.5, 2160, 3840)),
                patch.object(video_compressor, "run_ffmpeg", side_effect=fake_ffmpeg),
            ):
                output_path = video_compressor.compress_for_instagram(input_path)

            self.assertLessEqual(output_path.stat().st_size, INSTAGRAM_TEMP_FILE_LIMIT_BYTES)

    def test_first_compression_attempt_above_retry_threshold_retries(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = _sized_file(Path(temp_dir) / "input.mp4", 140)
            output_sizes = [58, 49]
            calls: list[Path] = []

            def fake_ffmpeg(**kwargs):
                calls.append(kwargs["output_path"])
                _sized_file(kwargs["output_path"], output_sizes.pop(0))
                return 8.0

            with (
                patch.object(video_compressor.shutil, "which", side_effect=lambda name: name),
                patch.object(video_compressor, "probe_video_metadata", return_value=VideoMetadata(100.0, 1080, 1920)),
                patch.object(video_compressor, "run_ffmpeg", side_effect=fake_ffmpeg),
            ):
                output_path = video_compressor.compress_for_instagram(input_path)

            self.assertEqual(len(calls), 2)
            self.assertFalse(calls[0].exists())
            self.assertEqual(output_path, calls[1])
            self.assertLessEqual(output_path.stat().st_size, 50 * BYTES_PER_MB)

    def test_all_attempts_above_limit_fail_before_upload(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            input_path = _sized_file(Path(temp_dir) / "input.mp4", 446)
            output_sizes = [70, 68, 72]
            calls: list[Path] = []

            def fake_ffmpeg(**kwargs):
                calls.append(kwargs["output_path"])
                _sized_file(kwargs["output_path"], output_sizes.pop(0))
                return 9.0

            with (
                patch.object(video_compressor.shutil, "which", side_effect=lambda name: name),
                patch.object(video_compressor, "probe_video_metadata", return_value=VideoMetadata(142.5, 1080, 1920)),
                patch.object(video_compressor, "run_ffmpeg", side_effect=fake_ffmpeg),
            ):
                with self.assertRaises(InstagramCompressionError):
                    video_compressor.compress_for_instagram(input_path)

            self.assertTrue(calls)
            self.assertFalse(calls[-1].exists())


def _install_main_import_stubs() -> None:
    requests = types.ModuleType("requests")
    requests.Timeout = TimeoutError
    requests.ConnectionError = ConnectionError
    requests.Response = object
    requests.request = Mock()
    sys.modules.setdefault("requests", requests)

    moviepy = types.ModuleType("moviepy")
    moviepy_editor = types.ModuleType("moviepy.editor")
    moviepy_editor.VideoFileClip = object
    sys.modules.setdefault("moviepy", moviepy)
    sys.modules.setdefault("moviepy.editor", moviepy_editor)

    google = types.ModuleType("google")
    googleapiclient = types.ModuleType("googleapiclient")
    googleapiclient_discovery = types.ModuleType("googleapiclient.discovery")
    googleapiclient_discovery.build = lambda *args, **kwargs: None
    googleapiclient_errors = types.ModuleType("googleapiclient.errors")
    googleapiclient_errors.HttpError = Exception
    googleapiclient_http = types.ModuleType("googleapiclient.http")
    googleapiclient_http.MediaFileUpload = object
    googleapiclient_http.MediaIoBaseDownload = object
    sys.modules.setdefault("google", google)
    sys.modules.setdefault("googleapiclient", googleapiclient)
    sys.modules.setdefault("googleapiclient.discovery", googleapiclient_discovery)
    sys.modules.setdefault("googleapiclient.errors", googleapiclient_errors)
    sys.modules.setdefault("googleapiclient.http", googleapiclient_http)

    google_oauth2 = types.ModuleType("google.oauth2")
    google_oauth2_credentials = types.ModuleType("google.oauth2.credentials")
    google_oauth2_credentials.Credentials = object
    google_auth = types.ModuleType("google.auth")
    google_auth_transport = types.ModuleType("google.auth.transport")
    google_auth_requests = types.ModuleType("google.auth.transport.requests")
    google_auth_requests.Request = object
    sys.modules.setdefault("google.oauth2", google_oauth2)
    sys.modules.setdefault("google.oauth2.credentials", google_oauth2_credentials)
    sys.modules.setdefault("google.auth", google_auth)
    sys.modules.setdefault("google.auth.transport", google_auth_transport)
    sys.modules.setdefault("google.auth.transport.requests", google_auth_requests)


class InstagramPipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        _install_main_import_stubs()
        global main
        from src import main

    def test_30_mb_input_uses_original_drive_url_without_compression(self) -> None:
        instagram = Mock()
        instagram.upload_reel.return_value = "ig-media-id"

        with (
            patch.object(main, "compress_for_instagram") as compress_mock,
            patch.object(main, "upload_temp_video") as upload_mock,
            patch.object(main, "delete_temp_drive_file") as delete_mock,
        ):
            result = main.upload_to_instagram_with_optional_compression(
                original_file_id="original-file-id",
                video_path=Path("original.mp4"),
                original_size=30 * BYTES_PER_MB,
                instagram=instagram,
                caption="caption",
            )

        self.assertEqual(result, "ig-media-id")
        instagram.upload_reel.assert_called_once_with(
            "https://drive.google.com/uc?export=download&id=original-file-id",
            "caption",
        )
        compress_mock.assert_not_called()
        upload_mock.assert_not_called()
        delete_mock.assert_not_called()

    def test_cleanup_occurs_after_instagram_success(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            compressed_path = _sized_file(Path(temp_dir) / "compressed.mp4", 49)
            instagram = Mock()
            instagram.upload_reel.return_value = "ig-media-id"

            with (
                patch.object(main, "compress_for_instagram", return_value=compressed_path),
                patch.object(main, "upload_temp_video", return_value="temp-file-id") as upload_mock,
                patch.object(main, "delete_temp_drive_file") as delete_mock,
            ):
                result = main.upload_to_instagram_with_optional_compression(
                    original_file_id="original-file-id",
                    video_path=Path("original.mp4"),
                    original_size=140 * BYTES_PER_MB,
                    instagram=instagram,
                    caption="caption",
                )

            self.assertEqual(result, "ig-media-id")
            upload_mock.assert_called_once_with(compressed_path)
            instagram.upload_reel.assert_called_once_with(
                "https://drive.google.com/uc?export=download&id=temp-file-id",
                "caption",
            )
            delete_mock.assert_called_once_with("temp-file-id")
            self.assertFalse(compressed_path.exists())

    def test_cleanup_occurs_after_instagram_failure(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            compressed_path = _sized_file(Path(temp_dir) / "compressed.mp4", 49)
            instagram = Mock()
            instagram.upload_reel.side_effect = RuntimeError("instagram failed")

            with (
                patch.object(main, "compress_for_instagram", return_value=compressed_path),
                patch.object(main, "upload_temp_video", return_value="temp-file-id"),
                patch.object(main, "delete_temp_drive_file") as delete_mock,
            ):
                with self.assertRaises(RuntimeError):
                    main.upload_to_instagram_with_optional_compression(
                        original_file_id="original-file-id",
                        video_path=Path("original.mp4"),
                        original_size=140 * BYTES_PER_MB,
                        instagram=instagram,
                        caption="caption",
                    )

            delete_mock.assert_called_once_with("temp-file-id")
            self.assertFalse(compressed_path.exists())

    def test_too_large_compressed_file_fails_before_temp_drive_upload(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            compressed_path = _sized_file(Path(temp_dir) / "compressed.mp4", 72)
            instagram = Mock()

            with (
                patch.object(main, "compress_for_instagram", return_value=compressed_path),
                patch.object(main, "upload_temp_video") as upload_mock,
                patch.object(main, "delete_temp_drive_file") as delete_mock,
            ):
                with self.assertRaises(ValueError):
                    main.upload_to_instagram_with_optional_compression(
                        original_file_id="original-file-id",
                        video_path=Path("original.mp4"),
                        original_size=446 * BYTES_PER_MB,
                        instagram=instagram,
                        caption="caption",
                    )

            upload_mock.assert_not_called()
            instagram.upload_reel.assert_not_called()
            delete_mock.assert_not_called()
            self.assertFalse(compressed_path.exists())

    def test_run_once_routes_separate_google_credentials(self) -> None:
        config = SimpleNamespace(
            google_client_id="client-id",
            google_client_secret="client-secret",
            google_workspace_refresh_token="workspace-refresh",
            google_youtube_refresh_token="youtube-refresh",
            google_sheet_id="sheet-id",
            google_drive_folder_id="folder-id",
            youtube_privacy_status="public",
            youtube_category_id="24",
            ig_access_token="ig-token",
            ig_business_account_id="ig-business-id",
            telegram_bot_token=None,
            telegram_chat_id=None,
            post_interval_days=2,
            low_queue_threshold=2,
            timezone="Asia/Kolkata",
            force_post=False,
        )
        sheets_instance = Mock()
        sheets_instance.read_rows.return_value = []
        drive_instance = Mock()

        with (
            patch.object(main, "build_google_credentials", side_effect=["workspace-creds", "youtube-creds"]) as auth_mock,
            patch.object(main, "SheetsClient", return_value=sheets_instance) as sheets_mock,
            patch.object(main, "DriveClient", return_value=drive_instance) as drive_mock,
            patch.object(main, "configure_temporary_drive_manager") as temp_manager_mock,
            patch.object(main, "YouTubeUploader") as youtube_mock,
            patch.object(main, "InstagramUploader"),
        ):
            main.run_once(config)

        auth_mock.assert_any_call("client-id", "client-secret", "workspace-refresh", main.WORKSPACE_SCOPES)
        auth_mock.assert_any_call("client-id", "client-secret", "youtube-refresh", main.YOUTUBE_SCOPES)
        sheets_mock.assert_called_once_with("workspace-creds", "sheet-id")
        drive_mock.assert_called_once_with("workspace-creds", "folder-id")
        temp_manager_mock.assert_called_once_with(drive_instance)
        youtube_mock.assert_called_once_with("youtube-creds", "public", "24")


if __name__ == "__main__":
    unittest.main()
