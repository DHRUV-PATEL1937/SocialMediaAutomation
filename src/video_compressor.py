from __future__ import annotations

import logging
import shutil
import subprocess
import time
from pathlib import Path


logger = logging.getLogger(__name__)


class VideoCompressionError(RuntimeError):
    pass


def compress_for_instagram(input_path: Path) -> Path:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise VideoCompressionError("FFmpeg is not installed or is not available on PATH.")

    output_path = input_path.with_name(f"{input_path.stem}.instagram-compressed.mp4")
    command = [
        ffmpeg,
        "-y",
        "-i",
        str(input_path),
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "23",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-movflags",
        "+faststart",
        str(output_path),
    ]

    started_at = time.monotonic()
    logger.info("Compressing %s for Instagram with FFmpeg.", input_path.name)
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            check=False,
            text=True,
        )
    except OSError as exc:
        raise VideoCompressionError(f"Failed to start FFmpeg: {exc}") from exc

    encoding_duration = time.monotonic() - started_at
    if completed.returncode != 0:
        raise VideoCompressionError(
            "FFmpeg compression failed with exit code "
            f"{completed.returncode}: {completed.stderr[-2000:]}"
        )
    if not output_path.exists() or output_path.stat().st_size == 0:
        raise VideoCompressionError("FFmpeg did not create a valid compressed output file.")

    logger.info("FFmpeg encoding duration: %.1fs", encoding_duration)
    return output_path
