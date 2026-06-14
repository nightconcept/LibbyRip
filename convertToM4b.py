#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from pathlib import PurePosixPath
from zipfile import ZipFile

from buildChapters import Metadata, metadata_to_ffmpeg


FFMPEG_BIN = [
    "ffmpeg",
    "-nostdin",
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


def is_zip(path: Path) -> bool:
    return path.suffix.lower() == ".zip"


def output_path_for(input_path: Path) -> Path:
    return input_path.with_suffix(".m4b")


def validate_input_file(input_path: Path) -> bool:
    if not input_path.exists():
        print(f"File not found: {input_path}", file=sys.stderr)
        return False

    if not input_path.is_file():
        print(f"Not a file: {input_path}", file=sys.stderr)
        return False

    return True


def convert_mp3(input_path: Path) -> bool:
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
            FFMPEG_BIN + ["-i", str(input_path)] + FFMPEG_SUFFIX + [str(temp_path)],
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


def is_safe_zip_member(member_name: str) -> bool:
    member_path = PurePosixPath(member_name)
    return not member_path.is_absolute() and ".." not in member_path.parts


def safe_extract_zip(zip_file: ZipFile, destination: Path) -> None:
    for member in zip_file.infolist():
        if not is_safe_zip_member(member.filename):
            raise ValueError(
                f"Refusing to extract suspicious ZIP entry: {member.filename}"
            )

        member_path = PurePosixPath(member.filename)
        target_path = destination.joinpath(*member_path.parts)

        if member.is_dir():
            target_path.mkdir(parents=True, exist_ok=True)
            continue

        target_path.parent.mkdir(parents=True, exist_ok=True)
        with zip_file.open(member) as source, target_path.open("wb") as target:
            shutil.copyfileobj(source, target)


def is_export_zip(input_path: Path) -> bool:
    try:
        with ZipFile(input_path) as zip_file:
            names = set(zip_file.namelist())
    except OSError:
        return False

    return (
        "metadata/metadata.json" in names
        and any(name.startswith("Part ") and name.endswith(".mp3") for name in names)
    )


def part_sort_key(path: Path) -> tuple[int, str]:
    stem = path.stem.removeprefix("Part ").strip()
    number = stem.split()[0]
    try:
        return (int(number), path.name)
    except ValueError:
        return (sys.maxsize, path.name)


def extracted_part_paths(extracted_dir: Path) -> list[Path]:
    return sorted(
        (
            path
            for path in extracted_dir.iterdir()
            if path.is_file() and is_mp3(path) and path.name.startswith("Part ")
        ),
        key=part_sort_key,
    )


def cover_path_for(extracted_dir: Path) -> Path | None:
    metadata_dir = extracted_dir / "metadata"
    if not metadata_dir.is_dir():
        return None
    covers = sorted(path for path in metadata_dir.iterdir() if path.name.startswith("cover."))
    return covers[0] if covers else None


def author_name_for(metadata: Metadata) -> str | None:
    return metadata.author or metadata.narrator


def escape_concat_filename(filename: str) -> str:
    return filename.replace("'", r"'\''")


def build_zip_ffmpeg_command(
    extracted_dir: Path,
    metadata_path: Path,
    cover_path: Path | None,
    output_path: Path,
    title: str,
    author: str | None,
    description: str | None,
) -> list[str]:
    command = [
        *FFMPEG_BIN,
        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        "files.txt",
        "-i",
        metadata_path.relative_to(extracted_dir).as_posix(),
    ]

    if cover_path is not None:
        command.extend(["-i", cover_path.relative_to(extracted_dir).as_posix()])

    command.extend(
        [
            "-map",
            "0:a",
            "-map_metadata",
            "1",
            "-map_chapters",
            "1",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-f",
            "ipod",
            "-metadata",
            f"title={title}",
            "-metadata",
            f"album={title}",
            "-metadata",
            "encoded_by=LibbyRip/LibreGRAB",
        ]
    )

    if author:
        command.extend(["-metadata", f"artist={author}", "-metadata", f"album_artist={author}"])

    if description:
        command.extend(["-metadata", f"comment={description}"])

    if cover_path is not None:
        command.extend(
            [
                "-map",
                "2:v",
                "-c:v",
                "copy",
                "-disposition:v:0",
                "attached_pic",
            ]
        )

    command.append(str(output_path))
    return command


def convert_export_zip(input_path: Path) -> bool:
    if not is_export_zip(input_path):
        print(
            f"Not a Libby export ZIP (missing metadata/metadata.json or Part *.mp3): {input_path}",
            file=sys.stderr,
        )
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
        with tempfile.TemporaryDirectory(
            prefix="libbyrip-zip-",
            dir=input_path.parent,
        ) as temp_dir:
            extracted_dir = Path(temp_dir)
            with ZipFile(input_path) as zip_file:
                safe_extract_zip(zip_file, extracted_dir)

            raw_metadata = json.loads(
                (extracted_dir / "metadata" / "metadata.json").read_text(encoding="utf-8")
            )
            metadata = Metadata.from_json(raw_metadata)
            part_paths = extracted_part_paths(extracted_dir)
            if not part_paths:
                print(f"No Part *.mp3 files found in export ZIP: {input_path}", file=sys.stderr)
                return False

            files_path = extracted_dir / "files.txt"
            files_path.write_text(
                "".join(
                    f"file '{escape_concat_filename(part.name)}'\n"
                    for part in part_paths
                ),
                encoding="utf-8",
            )
            ffmetadata_path = extracted_dir / "metadata.ffmeta"
            ffmetadata_path.write_text(
                metadata_to_ffmpeg(metadata),
                encoding="utf-8",
            )

            command = build_zip_ffmpeg_command(
                extracted_dir,
                ffmetadata_path,
                cover_path_for(extracted_dir),
                temp_path,
                metadata.title,
                author_name_for(metadata),
                raw_metadata.get("description", "").replace("\r", " ").replace("\n", " "),
            )
            subprocess.run(
                command,
                check=True,
                stdin=subprocess.DEVNULL,
                cwd=extracted_dir,
            )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"Error converting {input_path}: {exc}", file=sys.stderr)
        temp_path.unlink(missing_ok=True)
        return False
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


def convert_one(input_path: Path) -> bool:
    if not validate_input_file(input_path):
        return False

    input_path = input_path.resolve()

    if is_mp3(input_path):
        return convert_mp3(input_path)

    if is_zip(input_path):
        return convert_export_zip(input_path)

    print("File MUST be an MP3 or Libby export ZIP to continue", file=sys.stderr)
    return False


def batch_convert_root_mp3() -> int:
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


def batch_convert_root_zip() -> int:
    zip_paths = sorted(
        path
        for path in Path.cwd().iterdir()
        if path.is_file() and is_zip(path)
    )

    if not zip_paths:
        print("No ZIP files found in the repository root")
        return 0

    converted = 0
    skipped = 0
    failed = 0

    for input_path in zip_paths:
        output_path = output_path_for(input_path)
        if output_path.exists():
            print(f"Skipping existing: {output_path}")
            skipped += 1
            continue

        if not is_export_zip(input_path):
            print(f"Skipping non-export ZIP: {input_path}")
            skipped += 1
            continue

        if convert_export_zip(input_path):
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
    parser = argparse.ArgumentParser(
        description="Convert MP3 audiobooks or Libby export ZIPs to M4B"
    )
    parser.add_argument(
        "path",
        nargs="?",
        help="Path to a single MP3 file or Libby export ZIP to convert",
    )
    parser.add_argument(
        "--all-mp3",
        action="store_true",
        help="Convert every root-level MP3 in the current directory",
    )
    parser.add_argument(
        "--all-zip",
        action="store_true",
        help="Convert every root-level Libby export ZIP in the current directory",
    )
    return parser.parse_args()


def main() -> int:
    if not ensure_ffmpeg():
        return 1

    args = parse_args()

    if sum(bool(option) for option in (args.path, args.all_mp3, args.all_zip)) > 1:
        print(
            "Error: pass either a single path, --all-mp3, or --all-zip",
            file=sys.stderr,
            flush=True,
        )
        return 1

    if args.all_mp3:
        return batch_convert_root_mp3()

    if args.all_zip:
        return batch_convert_root_zip()

    if args.path:
        return 0 if convert_one(Path(args.path)) else 1

    path = input("MP3 or ZIP path: ").strip()
    if not path:
        print("File not found", file=sys.stderr, flush=True)
        return 1
    return 0 if convert_one(Path(path)) else 1


if __name__ == "__main__":
    raise SystemExit(main())
