from __future__ import annotations

import logging
import re
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from dateutil import parser
from moviepy.editor import VideoFileClip

from src.config import Config
from src.drive_client import DriveClient
from src.google_auth import build_google_credentials
from src.instagram_uploader import InstagramUploader
from src.notifier import Notifier
from src.sheets_client import SheetRow, SheetsClient
from src.youtube_uploader import YouTubeUploader


logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


PARTIAL_STATUSES = {"posted_yt_only", "posted_ig_only"}
POSTABLE_STATUSES = {"pending"} | PARTIAL_STATUSES
MAX_VIDEO_DURATION = 180  # seconds (3 minutes)


def main() -> None:
    config = Config.from_env()
    notifier = Notifier(config.telegram_bot_token, config.telegram_chat_id)

    try:
        result = run_once(config)
        if result.should_notify:
            notifier.send(result.message)
        logger.info(result.message)
    except Exception as exc:
        logger.exception("Run failed")
        notifier.send(f"Shorts auto-uploader failed:\n{type(exc).__name__}: {exc}")
        raise


class RunResult:
    def __init__(self, message: str, should_notify: bool) -> None:
        self.message = message
        self.should_notify = should_notify


def run_once(config: Config) -> RunResult:
    timezone = ZoneInfo(config.timezone)
    now = datetime.now(timezone)
    credentials = build_google_credentials(
        config.google_client_id,
        config.google_client_secret,
        config.google_refresh_token,
    )

    sheets = SheetsClient(credentials, config.google_sheet_id)
    drive = DriveClient(credentials, config.google_drive_folder_id)
    youtube = YouTubeUploader(credentials, config.youtube_privacy_status, config.youtube_category_id)
    instagram = InstagramUploader(config.ig_access_token, config.ig_business_account_id)

    rows = sheets.read_rows()
    pending_count = sum(1 for row in rows if row.status in POSTABLE_STATUSES)
    if pending_count <= config.low_queue_threshold:
        logger.warning("Low queue: only %s postable videos remain.", pending_count)

    last_posted_at = latest_posted_at(rows)
    if last_posted_at and now < last_posted_at + timedelta(days=config.post_interval_days):
        due_at = last_posted_at + timedelta(days=config.post_interval_days)
        return RunResult(f"Not due yet. Next post is due at {due_at.isoformat()}.", False)

    row = next((item for item in rows if item.status in POSTABLE_STATUSES), None)
    if row is None:
        return RunResult("No pending videos found in the sheet.", True)
    if not row.caption:
        return RunResult(f"Skipped {row.filename}: caption is empty.", True)

    drive_files = drive.list_video_files()
    file_info = drive_files.get(row.filename)
    if not file_info:
        return RunResult(f"Skipped {row.filename}: matching file was not found in Drive.", True)

    platform_ids = parse_platform_ids(row.platform_ids)
    with tempfile.TemporaryDirectory() as temp_dir:
        video_path = Path(temp_dir) / safe_filename(row.filename)
        drive.download_file(file_info["id"], video_path)
        validate_short_video(video_path)

        if "youtube" not in platform_ids:
            title = row.title or title_from_filename(row.filename)
            platform_ids["youtube"] = youtube.upload(video_path, title, row.caption)
            sheets.update_cells(row.row_number, {"status": "posted_yt_only", "platform_ids": format_platform_ids(platform_ids)})

        if "instagram" not in platform_ids:
            video_url = DriveClient.public_download_url(file_info["id"])
            platform_ids["instagram"] = instagram.upload_reel(video_url, row.caption)
            sheets.update_cells(row.row_number, {"status": "posted_ig_only", "platform_ids": format_platform_ids(platform_ids)})

    final_status = status_from_platform_ids(platform_ids)
    posted_at = now if final_status == "posted" else None
    sheets.update_post_result(row, final_status, posted_at, format_platform_ids(platform_ids))

    low_queue_note = ""
    if pending_count - 1 <= config.low_queue_threshold:
        low_queue_note = f"\nLow queue warning: {pending_count - 1} postable videos left."

    return RunResult(
        "Posted video successfully:\n"
        f"File: {row.filename}\n"
        f"YouTube: https://youtu.be/{platform_ids.get('youtube', 'not-posted')}\n"
        f"Instagram media id: {platform_ids.get('instagram', 'not-posted')}"
        f"{low_queue_note}",
        True,
    )


def latest_posted_at(rows: list[SheetRow]) -> datetime | None:
    posted_dates: list[datetime] = []
    for row in rows:
        if row.status == "posted" and row.posted_at:
            posted_dates.append(parser.isoparse(row.posted_at))
    return max(posted_dates) if posted_dates else None


def parse_platform_ids(value: str) -> dict[str, str]:
    result: dict[str, str] = {}
    if not value:
        return result
    for chunk in value.split(","):
        if ":" in chunk:
            platform, platform_id = chunk.split(":", 1)
            result[platform.strip().lower()] = platform_id.strip()
    return result


def format_platform_ids(platform_ids: dict[str, str]) -> str:
    return ",".join(f"{platform}:{platform_id}" for platform, platform_id in sorted(platform_ids.items()))


def status_from_platform_ids(platform_ids: dict[str, str]) -> str:
    has_youtube = bool(platform_ids.get("youtube"))
    has_instagram = bool(platform_ids.get("instagram"))
    if has_youtube and has_instagram:
        return "posted"
    if has_youtube:
        return "posted_yt_only"
    if has_instagram:
        return "posted_ig_only"
    return "pending"


def validate_short_video(video_path: Path) -> None:
    with VideoFileClip(str(video_path)) as clip:
        duration = float(clip.duration or 0)
        width, height = clip.size
    if duration > MAX_VIDEO_DURATION:
        raise ValueError(
            f"{video_path.name} is {duration:.1f}s long. "
            f"Videos should be {MAX_VIDEO_DURATION}s or less."
        )
    if height <= width:
        raise ValueError(f"{video_path.name} is not vertical. Detected {width}x{height}.")


def title_from_filename(filename: str) -> str:
    stem = Path(filename).stem
    title = re.sub(r"[_-]+", " ", stem).strip()
    return title[:100] or "Short video"


def safe_filename(filename: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]", "_", filename)


if __name__ == "__main__":
    main()
