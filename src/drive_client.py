from __future__ import annotations

import io
from pathlib import Path
from typing import Any

from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload


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

    @staticmethod
    def public_download_url(file_id: str) -> str:
        return f"https://drive.google.com/uc?export=download&id={file_id}"
