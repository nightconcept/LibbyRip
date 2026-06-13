#!/usr/bin/env python3
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


FFMPEG_PREFIX = [
    "ffmpeg",
    "-nostdin",
    "-i",
]

FFMPEG_SUFFIX = [
    "-c:a",
    "aac",
    "-b:a",
    "128k",
    "-vn",
    "-map_metadata",
    "0",
    "-map_chapters",
    "0",
    "-f",
    "ipod",
]


def ensure_ffmpeg() -> bool:
    try:
        subprocess.run(
            ("ffmpeg", "-version"),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=True,
        )
    except FileNotFoundError:
        print(
            "Error: FFmpeg not found, please install it on your system to continue: "
            "https://www.ffmpeg.org/download.html",
            file=sys.stderr,
        )
        return False
    except subprocess.CalledProcessError:
        print("Error: FFmpeg is installed but could not be executed", file=sys.stderr)
        return False

    return True


def is_mp3(path: Path) -> bool:
    return path.suffix.lower() == ".mp3"


def output_path_for(input_path: Path) -> Path:
    return input_path.with_suffix(".m4b")


def convert_one(input_path: Path) -> bool:
    if not input_path.exists():
        print(f"File not found: {input_path}", file=sys.stderr)
        return False

    if not input_path.is_file():
        print(f"Not a file: {input_path}", file=sys.stderr)
        return False

    if not is_mp3(input_path):
        print("File MUST be an mp3 file to continue", file=sys.stderr)
        return False

    output_path = output_path_for(input_path)
    temp_path = output_path.with_name(f"{output_path.stem}.partial.m4a")
    if output_path.exists():
        temp_path.unlink(missing_ok=True)
        print(f"Skipping existing: {output_path}", flush=True)
        return True

    temp_path.unlink(missing_ok=True)

    print(f"Converting: {input_path} -> {output_path}", flush=True)

    try:
        subprocess.run(
            FFMPEG_PREFIX + [str(input_path)] + FFMPEG_SUFFIX + [str(temp_path)],
            check=True,
            stdin=subprocess.DEVNULL,
        )
    except subprocess.CalledProcessError as exc:
        print(
            f"Error converting {input_path}: ffmpeg exited with code {exc.returncode}",
            file=sys.stderr,
        )
        temp_path.unlink(missing_ok=True)
        return False
    except KeyboardInterrupt:
        temp_path.unlink(missing_ok=True)
        raise

    temp_path.replace(output_path)
    print(f"Created: {output_path}", flush=True)
    return True


def batch_convert_root() -> int:
    mp3s = sorted(
        path
        for path in Path.cwd().iterdir()
        if path.is_file() and is_mp3(path)
    )

    if not mp3s:
        print("No MP3 files found in the repository root")
        return 0

    converted = 0
    skipped = 0
    failed = 0

    for input_path in mp3s:
        output_path = output_path_for(input_path)
        if output_path.exists():
            print(f"Skipping existing: {output_path}")
            skipped += 1
            continue

        if convert_one(input_path):
            converted += 1
        else:
            failed += 1

    print(
        f"Done: {converted} converted, {skipped} skipped, {failed} failed",
        file=sys.stderr if failed else sys.stdout,
        flush=True,
    )
    return 1 if failed else 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Convert MP3 audiobooks to M4B")
    parser.add_argument(
        "path",
        nargs="?",
        help="Path to a single MP3 file to convert",
    )
    parser.add_argument(
        "--all-mp3",
        action="store_true",
        help="Convert every root-level MP3 in the current directory",
    )
    return parser.parse_args()


def main() -> int:
    if not ensure_ffmpeg():
        return 1

    args = parse_args()

    if args.all_mp3 and args.path:
        print(
            "Error: pass either a single MP3 path or --all-mp3, not both",
            file=sys.stderr,
            flush=True,
        )
        return 1

    if args.all_mp3:
        return batch_convert_root()

    if args.path:
        return 0 if convert_one(Path(args.path)) else 1

    path = input("MP3 path: ").strip()
    if not path:
        print("File not found", file=sys.stderr, flush=True)
        return 1
    return 0 if convert_one(Path(path)) else 1


if __name__ == "__main__":
    raise SystemExit(main())
