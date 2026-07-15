from __future__ import annotations

import os
from dataclasses import dataclass


def _env(name: str, required: bool = True, default: str | None = None) -> str | None:
    value = os.getenv(name, default)
    if required and not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


@dataclass(frozen=True)
class Config:
    google_client_id: str
    google_client_secret: str
    google_refresh_token: str
    google_drive_folder_id: str
    google_sheet_id: str
    ig_access_token: str
    ig_business_account_id: str
    telegram_bot_token: str | None
    telegram_chat_id: str | None
    post_interval_days: int
    youtube_privacy_status: str
    youtube_category_id: str
    low_queue_threshold: int
    timezone: str

    @classmethod
    def from_env(cls) -> "Config":
        config = cls(
            google_client_id=_env("GOOGLE_CLIENT_ID"),
            google_client_secret=_env("GOOGLE_CLIENT_SECRET"),
            google_refresh_token=_env("GOOGLE_REFRESH_TOKEN"),
            google_drive_folder_id=_env("GOOGLE_DRIVE_FOLDER_ID"),
            google_sheet_id=_env("GOOGLE_SHEET_ID"),
            ig_access_token=_env("IG_ACCESS_TOKEN"),
            ig_business_account_id=_env("IG_BUSINESS_ACCOUNT_ID"),
            telegram_bot_token=_env("TELEGRAM_BOT_TOKEN", required=False),
            telegram_chat_id=_env("TELEGRAM_CHAT_ID", required=False),
            post_interval_days=int(_env("POST_INTERVAL_DAYS", required=False, default="2")),
            youtube_privacy_status=_env("YOUTUBE_PRIVACY_STATUS", required=False, default="public"),
            youtube_category_id=_env("YOUTUBE_CATEGORY_ID", required=False, default="24"),
            low_queue_threshold=int(_env("LOW_QUEUE_THRESHOLD", required=False, default="2")),
            timezone=_env("TIMEZONE", required=False, default="Asia/Kolkata"),
        )
        print("Loaded IG_BUSINESS_ACCOUNT_ID:", repr(config.ig_business_account_id))
        print("Loaded IG_BUSINESS_ACCOUNT_ID length:", len(config.ig_business_account_id))
        print("Loaded IG_BUSINESS_ACCOUNT_ID startswith:", config.ig_business_account_id[:6])
        print("Loaded IG_BUSINESS_ACCOUNT_ID endswith:", config.ig_business_account_id[-6:])
        return config
