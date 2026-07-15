from __future__ import annotations

from pathlib import Path
from typing import Any

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload


class YouTubeUploader:
    def __init__(self, credentials: Any, privacy_status: str = "public", category_id: str = "24") -> None:
        self.service = build("youtube", "v3", credentials=credentials, cache_discovery=False)
        self.privacy_status = privacy_status
        self.category_id = category_id

    def upload(self, video_path: Path, title: str, caption: str) -> str:
        description = caption if "#shorts" in caption.lower() else f"{caption}\n\n#Shorts"
        body = {
            "snippet": {
                "title": title[:100],
                "description": description,
                "categoryId": self.category_id,
            },
            "status": {
                "privacyStatus": self.privacy_status,
                "selfDeclaredMadeForKids": False,
            },
        }

        media = MediaFileUpload(str(video_path), chunksize=8 * 1024 * 1024, resumable=True)
        request = self.service.videos().insert(part="snippet,status", body=body, media_body=media)

        response = None
        while response is None:
            _, response = request.next_chunk()
        return response["id"]
