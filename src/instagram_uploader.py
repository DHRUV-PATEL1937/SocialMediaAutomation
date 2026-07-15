from __future__ import annotations

import time

import requests


GRAPH_BASE = "https://graph.facebook.com/v20.0"


class InstagramUploader:
    def __init__(self, access_token: str, ig_business_account_id: str) -> None:
        self.access_token = access_token
        self.ig_business_account_id = ig_business_account_id

    def upload_reel(self, video_url: str, caption: str) -> str:
        creation_id = self._create_container(video_url, caption)
        self._wait_until_ready(creation_id)
        return self._publish_container(creation_id)

    def _create_container(self, video_url: str, caption: str) -> str:
        response = requests.post(
            f"{GRAPH_BASE}/{self.ig_business_account_id}/media",
            data={
                "media_type": "REELS",
                "video_url": video_url,
                "caption": caption,
                "access_token": self.access_token,
            },
            timeout=60,
        )
        response.raise_for_status()
        payload = response.json()
        if "id" not in payload:
            raise RuntimeError(f"Instagram did not return a creation id: {payload}")
        return payload["id"]

    def _wait_until_ready(self, creation_id: str, max_attempts: int = 30) -> None:
        for attempt in range(1, max_attempts + 1):
            response = requests.get(
                f"{GRAPH_BASE}/{creation_id}",
                params={"fields": "status_code,status", "access_token": self.access_token},
                timeout=30,
            )
            response.raise_for_status()
            payload = response.json()
            status = payload.get("status_code")
            if status == "FINISHED":
                return
            if status == "ERROR":
                raise RuntimeError(f"Instagram container failed: {payload}")
            time.sleep(min(10 + attempt * 2, 60))
        raise TimeoutError("Instagram container was not ready before the polling timeout.")

    def _publish_container(self, creation_id: str) -> str:
        response = requests.post(
            f"{GRAPH_BASE}/{self.ig_business_account_id}/media_publish",
            data={"creation_id": creation_id, "access_token": self.access_token},
            timeout=60,
        )
        response.raise_for_status()
        payload = response.json()
        if "id" not in payload:
            raise RuntimeError(f"Instagram did not return a media id: {payload}")
        return payload["id"]
