from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable

from googleapiclient.errors import HttpError
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload


TRANSIENT_GOOGLE_STATUS_CODES = {408, 429, 500, 502, 503, 504}


class DriveClient:
    def __init__(self, credentials: Any, folder_id: str) -> None:
        self.folder_id = folder_id
        self.service = build("drive", "v3", credentials=credentials, cache_discovery=False)

    def list_video_files(self) -> dict[str, dict[str, str]]:
        query = (
            f"'{self.folder_id}' in parents and trashed = false "
            "and mimeType contains 'video/'"
        )
        files: dict[str, dict[str, str]] = {}
        page_token = None
        while True:
            response = (
                self.service.files()
                .list(
                    q=query,
                    spaces="drive",
                    fields="nextPageToken, files(id, name, mimeType, webContentLink)",
                    pageToken=page_token,
                )
                .execute()
            )
            for item in response.get("files", []):
                files[item["name"]] = item
            page_token = response.get("nextPageToken")
            if not page_token:
                return files

    def download_file(self, file_id: str, target_path: Path) -> Path:
        request = self.service.files().get_media(fileId=file_id)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with target_path.open("wb") as handle:
            downloader = MediaIoBaseDownload(handle, request)
            done = False
            while not done:
                _, done = downloader.next_chunk()
        return target_path

    def upload_file(self, file_path: Path, name: str | None = None, mime_type: str = "video/mp4") -> str:
        metadata = {"name": name or file_path.name, "parents": [self.folder_id]}
        response = self._execute_with_retries(
            lambda: self.service.files().create(
                body=metadata,
                media_body=MediaFileUpload(str(file_path), mimetype=mime_type, resumable=True),
                fields="id",
            )
        )
        file_id = response.get("id")
        if not file_id:
            raise RuntimeError(f"Google Drive upload did not return a file id: {response}")
        return file_id

    def delete_file(self, file_id: str) -> None:
        self._execute_with_retries(lambda: self.service.files().delete(fileId=file_id))

    def make_public(self, file_id: str) -> None:
        self._execute_with_retries(
            lambda: self.service.permissions().create(
                fileId=file_id,
                body={"type": "anyone", "role": "reader"},
                fields="id",
            )
        )

    @staticmethod
    def public_download_url(file_id: str) -> str:
        return f"https://drive.google.com/uc?export=download&id={file_id}"

    @staticmethod
    def _execute_with_retries(request_factory: Callable[[], Any], max_attempts: int = 5) -> dict[str, Any]:
        for attempt in range(1, max_attempts + 1):
            try:
                response = request_factory().execute()
                return response or {}
            except HttpError as exc:
                status = getattr(exc.resp, "status", None)
                if status not in TRANSIENT_GOOGLE_STATUS_CODES or attempt >= max_attempts:
                    raise
                time.sleep(min(2 ** (attempt - 1), 30))
        raise RuntimeError("Google Drive request failed after retry attempts.")
