from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import json
import pathlib
import struct
import subprocess
import zlib


SYNC_KEYS = ("width", "height", "fps_num", "fps_den", "frames")
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def expected_frame_count(duration: Decimal, fps_num: int, fps_den: int) -> int:
    value = duration * Decimal(fps_num) / Decimal(fps_den)
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def probe_media(path: pathlib.Path) -> dict:
    result = subprocess.run(
        [
            "ffprobe", "-v", "error", "-count_frames",
            "-show_entries",
            "stream=codec_type,width,height,r_frame_rate,nb_read_frames,start_pts,time_base,start_time:format=duration",
            "-of", "json", str(path),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)
    video = next((stream for stream in payload["streams"] if stream["codec_type"] == "video"), None)
    if video is None:
        raise ValueError(f"no video stream: {path}")
    fps_num, fps_den = (int(value) for value in video["r_frame_rate"].split("/", 1))
    return {
        "path": str(path.resolve()),
        "width": int(video["width"]),
        "height": int(video["height"]),
        "fps_num": fps_num,
        "fps_den": fps_den,
        "frames": int(video["nb_read_frames"]),
        "duration": float(payload["format"]["duration"]),
        "start_pts": int(video["start_pts"]),
        "time_base": video["time_base"],
        "start_time": float(video["start_time"]),
    }


def validate_sync(source: dict, matte: dict) -> list[str]:
    failures = [key for key in SYNC_KEYS if source.get(key) != matte.get(key)]
    source_time_base = source.get("time_base")
    matte_time_base = matte.get("time_base")
    if source_time_base is None or source_time_base != matte_time_base:
        failures.append("time_base")
    source_start_pts = source.get("start_pts")
    matte_start_pts = matte.get("start_pts")
    if source_start_pts != matte_start_pts or source_start_pts != 0 or matte_start_pts != 0:
        failures.append("start_pts")
    try:
        start_times_are_zero = (
            abs(float(source["start_time"])) <= 1e-9
            and abs(float(matte["start_time"])) <= 1e-9
        )
    except (KeyError, TypeError, ValueError):
        start_times_are_zero = False
    if not start_times_are_zero:
        failures.append("start_time")
    return failures


def sha256_file(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_matte_statistics(stats: dict) -> list[str]:
    failures = []
    if not 0.02 <= stats["mean_coverage"] <= 0.90:
        failures.append("mean_coverage")
    if stats["max_coverage_jump"] > 0.20:
        failures.append("max_coverage_jump")
    if stats["max_low_coverage_run"] > 2:
        failures.append("max_low_coverage_run")
    if stats["max_non_person_island"] > 0.005:
        failures.append("max_non_person_island")
    return failures


def _paeth_predictor(left: int, up: int, upper_left: int) -> int:
    estimate = left + up - upper_left
    left_distance = abs(estimate - left)
    up_distance = abs(estimate - up)
    upper_left_distance = abs(estimate - upper_left)
    if left_distance <= up_distance and left_distance <= upper_left_distance:
        return left
    if up_distance <= upper_left_distance:
        return up
    return upper_left


def _read_grayscale_png(path: pathlib.Path) -> tuple[int, int, bytes]:
    try:
        payload = path.read_bytes()
    except OSError as error:
        raise ValueError(f"unreadable matte frame: {path}") from error
    if not payload.startswith(PNG_SIGNATURE):
        raise ValueError(f"invalid PNG matte frame: {path}")

    offset = len(PNG_SIGNATURE)
    ihdr = None
    idat_parts = []
    saw_iend = False
    chunk_index = 0
    while offset < len(payload):
        if offset + 12 > len(payload):
            raise ValueError(f"truncated PNG chunk: {path}")
        length = struct.unpack(">I", payload[offset:offset + 4])[0]
        kind = payload[offset + 4:offset + 8]
        data_start = offset + 8
        data_end = data_start + length
        crc_end = data_end + 4
        if crc_end > len(payload):
            raise ValueError(f"truncated PNG chunk: {path}")
        chunk_data = payload[data_start:data_end]
        expected_crc = struct.unpack(">I", payload[data_end:crc_end])[0]
        actual_crc = zlib.crc32(kind + chunk_data) & 0xFFFFFFFF
        if actual_crc != expected_crc:
            raise ValueError(f"invalid PNG checksum: {path}")
        offset = crc_end

        if kind == b"IHDR":
            if chunk_index != 0 or ihdr is not None or length != 13:
                raise ValueError(f"invalid PNG IHDR: {path}")
            ihdr = chunk_data
        elif kind == b"IDAT":
            idat_parts.append(chunk_data)
        elif kind == b"IEND":
            if length != 0 or offset != len(payload):
                raise ValueError(f"invalid PNG IEND: {path}")
            saw_iend = True
            break
        chunk_index += 1

    if ihdr is None or not idat_parts or not saw_iend:
        raise ValueError(f"incomplete PNG matte frame: {path}")

    width, height, bit_depth, color_type, compression, filter_method, interlace = struct.unpack(
        ">IIBBBBB", ihdr
    )
    if width <= 0 or height <= 0:
        raise ValueError(f"invalid PNG dimensions: {path}")
    if bit_depth != 8 or color_type != 0:
        raise ValueError(f"matte frame must be an 8-bit grayscale single-channel PNG: {path}")
    if compression != 0 or filter_method != 0 or interlace != 0:
        raise ValueError(f"unsupported PNG encoding: {path}")

    try:
        scanlines = zlib.decompress(b"".join(idat_parts))
    except zlib.error as error:
        raise ValueError(f"invalid PNG image data: {path}") from error
    expected_size = height * (width + 1)
    if len(scanlines) != expected_size:
        raise ValueError(f"invalid PNG scanline size: {path}")

    pixels = bytearray()
    previous = bytearray(width)
    cursor = 0
    for _ in range(height):
        filter_type = scanlines[cursor]
        cursor += 1
        encoded = scanlines[cursor:cursor + width]
        cursor += width
        reconstructed = bytearray(width)
        for index, value in enumerate(encoded):
            left = reconstructed[index - 1] if index else 0
            up = previous[index]
            upper_left = previous[index - 1] if index else 0
            if filter_type == 0:
                predictor = 0
            elif filter_type == 1:
                predictor = left
            elif filter_type == 2:
                predictor = up
            elif filter_type == 3:
                predictor = (left + up) // 2
            elif filter_type == 4:
                predictor = _paeth_predictor(left, up, upper_left)
            else:
                raise ValueError(f"unsupported PNG filter {filter_type}: {path}")
            reconstructed[index] = (value + predictor) & 0xFF
        pixels.extend(reconstructed)
        previous = reconstructed
    return width, height, bytes(pixels)


def matte_statistics(
    paths: Sequence[pathlib.Path],
    reviewed_max_non_person_island: float,
) -> dict:
    if not 0.0 <= reviewed_max_non_person_island <= 1.0:
        raise ValueError("reviewed_max_non_person_island must be between 0 and 1")
    paths = tuple(pathlib.Path(path) for path in paths)
    if not paths:
        raise ValueError("matte sequence must be non-empty")
    for index, path in enumerate(paths):
        expected_name = f"matte_{index:06d}.png"
        if path.name != expected_name:
            raise ValueError(
                f"invalid matte sequence name: expected {expected_name}, got {path.name}"
            )

    coverages = []
    low_run = 0
    max_low_run = 0
    dimensions = None
    for path in paths:
        width, height, pixels = _read_grayscale_png(path)
        if dimensions is None:
            dimensions = (width, height)
        elif dimensions != (width, height):
            raise ValueError("matte sequence must use consistent dimensions")
        coverage = sum(pixel > 8 for pixel in pixels) / len(pixels)
        coverages.append(coverage)
        low_run = low_run + 1 if coverage < 0.01 else 0
        max_low_run = max(max_low_run, low_run)
    max_coverage_jump = max(
        (abs(current - previous) for previous, current in zip(coverages, coverages[1:])),
        default=0.0,
    )
    width, height = dimensions
    return {
        "mean_coverage": sum(coverages) / len(coverages),
        "max_coverage_jump": max_coverage_jump,
        "max_low_coverage_run": int(max_low_run),
        "max_non_person_island": float(reviewed_max_non_person_island),
        "frames": len(paths),
        "width": width,
        "height": height,
    }
