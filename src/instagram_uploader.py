from __future__ import annotations

import random
import time
from dataclasses import dataclass
from typing import Any

import requests


GRAPH_API_VERSION = "v26.0"
GRAPH_BASE = f"https://graph.facebook.com/{GRAPH_API_VERSION}"
TRANSIENT_STATUS_CODES = {408, 425, 429, 500, 502, 503, 504}
TERMINAL_FAILURE_STATUSES = {"ERROR", "EXPIRED"}
READY_STATUSES = {"FINISHED", "PUBLISHED"}


class InstagramApiError(RuntimeError):
    pass


@dataclass
class _UploadState:
    creation_id: str | None = None
    media_id: str | None = None


class InstagramUploader:
    def __init__(self, access_token: str, ig_business_account_id: str) -> None:
        self.access_token = access_token
        self.ig_business_account_id = ig_business_account_id

    def upload_reel(self, video_url: str, caption: str) -> str:
        state = _UploadState()
        creation_id = self._create_container(video_url, caption, state)
        self._wait_until_ready(creation_id)
        return self._publish_container(creation_id, state)

    def _create_container(self, video_url: str, caption: str, state: _UploadState) -> str:
        if state.creation_id:
            return state.creation_id

        print("=" * 60)
        print("GRAPH_BASE:", GRAPH_BASE)
        print("IG BUSINESS ID:", self.ig_business_account_id)
        print("IG Business ID repr:", repr(self.ig_business_account_id))
        print("IG Business ID length:", len(self.ig_business_account_id))
        print("IG_BUSINESS_ACCOUNT_ID startswith:", self.ig_business_account_id[:6])
        print("IG_BUSINESS_ACCOUNT_ID endswith:", self.ig_business_account_id[-6:])
        print("REQUEST URL:", f"{GRAPH_BASE}/{self.ig_business_account_id}/media")
        print("ACCESS TOKEN PREFIX:", self.access_token[:20] + "...")
        print("VIDEO URL:", video_url[:100])
        print("=" * 60)

        data = {
            "media_type": "REELS",
            "video_url": video_url,
            "caption": caption,
            "access_token": self.access_token,
        }
        print("===== META REQUEST DATA =====")
        print({
            "media_type": "REELS",
            "video_url": video_url,
            "caption": caption,
        })
        print("=============================")

        payload = self._request(
            "POST",
            f"{GRAPH_BASE}/{self.ig_business_account_id}/media",
            data=data,
            timeout=60,
        )
        if "id" not in payload:
            raise InstagramApiError(f"Instagram did not return a creation id: {payload}")
        state.creation_id = payload["id"]
        return state.creation_id

    def _wait_until_ready(self, creation_id: str, max_attempts: int = 30) -> None:
        for attempt in range(1, max_attempts + 1):
            payload = self._request(
                "GET",
                f"{GRAPH_BASE}/{creation_id}",
                params={"fields": "status_code,status", "access_token": self.access_token},
                timeout=30,
            )
            status = str(payload.get("status_code", "")).upper()
            if status in READY_STATUSES:
                return
            if status in TERMINAL_FAILURE_STATUSES:
                raise InstagramApiError(f"Instagram container failed with status {status}: {payload}")
            self._sleep_with_backoff(attempt, base_delay=10, max_delay=60)
        raise TimeoutError(f"Instagram container {creation_id} was not ready before the polling timeout.")

    def _publish_container(self, creation_id: str, state: _UploadState) -> str:
        if state.media_id:
            return state.media_id

        payload = self._request(
            "POST",
            f"{GRAPH_BASE}/{self.ig_business_account_id}/media_publish",
            data={"creation_id": creation_id, "access_token": self.access_token},
            timeout=60,
        )
        if "id" not in payload:
            raise InstagramApiError(f"Instagram did not return a media id: {payload}")
        state.media_id = payload["id"]
        return state.media_id

    def _request(
        self,
        method: str,
        url: str,
        max_attempts: int = 5,
        **kwargs: Any,
    ) -> dict[str, Any]:
        last_error: Exception | None = None
        data = kwargs.get("data")
        params = kwargs.get("params")
        headers = kwargs.get("headers")
        timeout = kwargs.get("timeout")
        for attempt in range(1, max_attempts + 1):
            try:
                self._print_request_debug(method, url, data, params, headers)
                response = requests.request(
                    method,
                    url,
                    data=data,
                    params=params,
                    headers=headers,
                    timeout=timeout,
                )
                print("===== META RESPONSE =====")
                print(response.status_code)
                print(response.text)
                print("=========================")
                if response.status_code in TRANSIENT_STATUS_CODES and attempt < max_attempts:
                    self._sleep_with_backoff(attempt)
                    continue
                self._raise_for_meta_error(response)
                return self._json(response)
            except (requests.Timeout, requests.ConnectionError) as exc:
                last_error = exc
                if attempt >= max_attempts:
                    break
                self._sleep_with_backoff(attempt)
        raise InstagramApiError(f"Instagram request failed after {max_attempts} attempts: {last_error}")

    @staticmethod
    def _print_request_debug(
        method: str,
        url: str,
        data: Any,
        params: Any,
        headers: Any,
    ) -> None:
        redacted_headers = dict(headers or {})
        if "Authorization" in redacted_headers:
            redacted_headers["Authorization"] = "<redacted>"
        if isinstance(data, dict) and "access_token" in data:
            data = {**data, "access_token": "<redacted>"}
        if isinstance(params, dict) and "access_token" in params:
            params = {**params, "access_token": "<redacted>"}

        print("===== FINAL HTTP REQUEST =====")
        print("Full URL:", url)
        print("HTTP method:", method)
        print("POST body:", data)
        print("Query parameters:", params)
        print("Request headers:", redacted_headers)
        print("==============================")

    def _raise_for_meta_error(self, response: requests.Response) -> None:
        if response.ok:
            return

        payload = self._safe_json(response)
        error = payload.get("error") if isinstance(payload, dict) else None
        if isinstance(error, dict):
            message = error.get("message", "Unknown Meta API error")
            error_type = error.get("type", "unknown_type")
            code = error.get("code", "unknown_code")
            subcode = error.get("error_subcode")
            fbtrace_id = error.get("fbtrace_id")
            details = [
                f"HTTP {response.status_code}",
                f"type={error_type}",
                f"code={code}",
            ]
            if subcode:
                details.append(f"subcode={subcode}")
            if fbtrace_id:
                details.append(f"fbtrace_id={fbtrace_id}")
            raise InstagramApiError(f"Instagram API error: {message} ({', '.join(details)})")

        raise InstagramApiError(f"Instagram API error: HTTP {response.status_code} {response.text[:500]}")

    @staticmethod
    def _json(response: requests.Response) -> dict[str, Any]:
        payload = response.json()
        if not isinstance(payload, dict):
            raise InstagramApiError(f"Instagram returned an unexpected response: {payload}")
        return payload

    @staticmethod
    def _safe_json(response: requests.Response) -> dict[str, Any]:
        try:
            payload = response.json()
            return payload if isinstance(payload, dict) else {}
        except ValueError:
            return {}

    @staticmethod
    def _sleep_with_backoff(attempt: int, base_delay: float = 1.0, max_delay: float = 30.0) -> None:
        delay = min(max_delay, base_delay * (2 ** (attempt - 1)))
        time.sleep(delay + random.uniform(0, delay * 0.2))
