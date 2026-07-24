from __future__ import annotations

import logging
import json
import shutil
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path


logger = logging.getLogger(__name__)

BYTES_PER_MB = 1024 * 1024
INSTAGRAM_TEMP_FILE_LIMIT_BYTES = 60 * BYTES_PER_MB
PREFERRED_TARGET_BYTES = 50 * BYTES_PER_MB
RETRY_TARGET_BYTES = [50 * BYTES_PER_MB, 45 * BYTES_PER_MB, 40 * BYTES_PER_MB]
RETRY_SIZE_TRIGGER_BYTES = 55 * BYTES_PER_MB
AUDIO_BITRATE_KBPS = 128
MIN_VIDEO_BITRATE_KBPS = 350
MAX_VERTICAL_WIDTH = 1080
MAX_VERTICAL_HEIGHT = 1920
MAX_LANDSCAPE_WIDTH = 1920
MAX_LANDSCAPE_HEIGHT = 1080


class InstagramCompressionError(RuntimeError):
    pass


VideoCompressionError = InstagramCompressionError


@dataclass(frozen=True)
class VideoMetadata:
    duration_seconds: float
    width: int
    height: int


def compress_for_instagram(input_path: Path) -> Path:
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        raise InstagramCompressionError("FFmpeg is not installed or is not available on PATH.")
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        raise InstagramCompressionError("ffprobe is not installed or is not available on PATH.")

    original_size = input_path.stat().st_size
    metadata = probe_video_metadata(input_path, ffprobe)
    output_width, output_height = instagram_safe_dimensions(metadata.width, metadata.height)

    logger.info("Instagram compression required.")
    logger.info("Original size: %.2f MB", bytes_to_mb(original_size))
    logger.info("Duration: %.1f seconds", metadata.duration_seconds)
    logger.info("Resolution: %sx%s", metadata.width, metadata.height)

    last_output_path: Path | None = None
    last_output_size: int | None = None
    for attempt, target_size in enumerate(RETRY_TARGET_BYTES, start=1):
        output_path = input_path.with_name(f"{input_path.stem}.instagram-compressed-attempt-{attempt}.mp4")
        video_bitrate = calculate_video_bitrate_kbps(target_size, metadata.duration_seconds)
        logger.info("Target size: %.0f MB", bytes_to_mb(target_size))
        logger.info("Calculated video bitrate: %s kbps", video_bitrate)
        logger.info("Compression attempt %s/%s", attempt, len(RETRY_TARGET_BYTES))
        logger.info("Output resolution: %sx%s", output_width, output_height)

        encoding_duration = run_ffmpeg(
            ffmpeg=ffmpeg,
            input_path=input_path,
            output_path=output_path,
            video_bitrate_kbps=video_bitrate,
            output_width=output_width,
            output_height=output_height,
        )
        output_size = output_path.stat().st_size
        logger.info("Compressed size: %.2f MB", bytes_to_mb(output_size))
        logger.info("Compression ratio: %.2f", output_size / original_size)
        logger.info("FFmpeg duration: %.1fs", encoding_duration)

        if last_output_path and last_output_path.exists():
            last_output_path.unlink()
        last_output_path = output_path
        last_output_size = output_size

        if output_size <= RETRY_SIZE_TRIGGER_BYTES:
            logger.info("Compression successful.")
            return output_path
        logger.warning(
            "Compression attempt %s produced %.2f MB, above retry threshold %.0f MB.",
            attempt,
            bytes_to_mb(output_size),
            bytes_to_mb(RETRY_SIZE_TRIGGER_BYTES),
        )

    if last_output_path and last_output_size is not None and last_output_size <= INSTAGRAM_TEMP_FILE_LIMIT_BYTES:
        logger.info("Compression finished below absolute limit after retries.")
        return last_output_path

    final_size = last_output_size or 0
    if last_output_path and last_output_path.exists():
        last_output_path.unlink()
    raise InstagramCompressionError(
        "Unable to compress video below Instagram temporary upload limit.\n"
        f"Original: {bytes_to_mb(original_size):.2f} MB\n"
        f"Final: {bytes_to_mb(final_size):.2f} MB\n"
        f"Limit: {bytes_to_mb(INSTAGRAM_TEMP_FILE_LIMIT_BYTES):.0f} MB"
    )


def probe_video_metadata(input_path: Path, ffprobe: str | None = None) -> VideoMetadata:
    ffprobe_binary = ffprobe or shutil.which("ffprobe")
    if not ffprobe_binary:
        raise InstagramCompressionError("ffprobe is not installed or is not available on PATH.")
    command = [
        ffprobe_binary,
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height:format=duration",
        "-of",
        "json",
        str(input_path),
    ]
    completed = subprocess.run(command, capture_output=True, check=False, text=True)
    if completed.returncode != 0:
        raise InstagramCompressionError(
            "ffprobe failed with exit code "
            f"{completed.returncode}: {completed.stderr[-2000:]}"
        )
    try:
        payload = json.loads(completed.stdout)
        stream = payload["streams"][0]
        duration = float(payload["format"]["duration"])
        width = int(stream["width"])
        height = int(stream["height"])
    except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise InstagramCompressionError(f"Unable to parse ffprobe output: {completed.stdout[:1000]}") from exc
    if duration <= 0 or width <= 0 or height <= 0:
        raise InstagramCompressionError(f"Invalid video metadata from ffprobe: {payload}")
    return VideoMetadata(duration_seconds=duration, width=width, height=height)


def calculate_video_bitrate_kbps(target_size_bytes: int, duration_seconds: float) -> int:
    total_bitrate_kbps = int((target_size_bytes * 8) / duration_seconds / 1000)
    return max(total_bitrate_kbps - AUDIO_BITRATE_KBPS, MIN_VIDEO_BITRATE_KBPS)


def instagram_safe_dimensions(width: int, height: int) -> tuple[int, int]:
    if height >= width:
        max_width = MAX_VERTICAL_WIDTH
        max_height = MAX_VERTICAL_HEIGHT
    else:
        max_width = MAX_LANDSCAPE_WIDTH
        max_height = MAX_LANDSCAPE_HEIGHT

    scale = min(max_width / width, max_height / height, 1.0)
    output_width = even_dimension(int(width * scale))
    output_height = even_dimension(int(height * scale))
    return output_width, output_height


def even_dimension(value: int) -> int:
    return max(2, value - (value % 2))


def run_ffmpeg(
    ffmpeg: str,
    input_path: Path,
    output_path: Path,
    video_bitrate_kbps: int,
    output_width: int,
    output_height: int,
) -> float:
    command = [
        ffmpeg,
        "-y",
        "-i",
        str(input_path),
        "-vf",
        f"scale={output_width}:{output_height}:force_original_aspect_ratio=decrease,format=yuv420p",
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-b:v",
        f"{video_bitrate_kbps}k",
        "-maxrate",
        f"{video_bitrate_kbps}k",
        "-bufsize",
        f"{video_bitrate_kbps * 2}k",
        "-c:a",
        "aac",
        "-b:a",
        f"{AUDIO_BITRATE_KBPS}k",
        "-movflags",
        "+faststart",
        str(output_path),
    ]

    started_at = time.monotonic()
    try:
        completed = subprocess.run(command, capture_output=True, check=False, text=True)
    except OSError as exc:
        raise InstagramCompressionError(f"Failed to start FFmpeg: {exc}") from exc

    encoding_duration = time.monotonic() - started_at
    if completed.returncode != 0:
        raise InstagramCompressionError(
            "FFmpeg compression failed with exit code "
            f"{completed.returncode}: {completed.stderr[-2000:]}"
        )
    if not output_path.exists() or output_path.stat().st_size == 0:
        raise InstagramCompressionError("FFmpeg did not create a valid compressed output file.")
    return encoding_duration


def bytes_to_mb(size: int) -> float:
    return size / BYTES_PER_MB
