from __future__ import annotations

import logging
from pathlib import Path

from src.drive_client import DriveClient


logger = logging.getLogger(__name__)

_drive_client: DriveClient | None = None


def configure_temporary_drive_manager(drive_client: DriveClient) -> None:
    global _drive_client
    _drive_client = drive_client


def upload_temp_video(file_path: Path) -> str:
    drive = _require_drive_client()
    file_id = drive.upload_file(file_path, name=f"instagram-temp-{file_path.name}")
    logger.info("Temporary Drive file ID: %s", file_id)
    try:
        drive.make_public(file_id)
        logger.info("Temporary Drive URL: %s", DriveClient.public_download_url(file_id))
        return file_id
    except Exception:
        try:
            drive.delete_file(file_id)
            logger.info("Deleted temporary Drive file after public permission failure: %s", file_id)
        except Exception as cleanup_error:
            logger.warning("Failed to delete temporary Drive file %s after upload failure: %s", file_id, cleanup_error)
        raise


def delete_temp_drive_file(file_id: str) -> None:
    drive = _require_drive_client()
    drive.delete_file(file_id)
    logger.info("Deleted temporary Drive file: %s", file_id)


def _require_drive_client() -> DriveClient:
    if _drive_client is None:
        raise RuntimeError("Temporary Drive manager has not been configured.")
    return _drive_client
