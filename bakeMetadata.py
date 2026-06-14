#!/usr/bin/env python3
import sys
import os
import json
import eyed3
import mimetypes
import argparse
from eyed3.id3 import ID3_V2_4

def bake_metadata(workingDir, progress_callback=None):
    if workingDir.startswith("'"):
        workingDir = workingDir[1:-1]
    # Sort the working list alphabetically
    workingList = sorted(os.listdir(workingDir))

    if "metadata" not in workingList:
        error_msg = "ERROR: Working directory MUST contain a metadata directory. Remember to click the 'Export audiobook' button in the website!"
        if progress_callback:
            progress_callback(error_msg, 0)
        raise FileNotFoundError(error_msg)

    cover = [f for f in os.listdir(os.path.join(workingDir, "metadata")) if f.startswith("cover")]
    if len(cover) != 1:
        error_msg = "ERROR: Cover art not found"
        if progress_callback:
            progress_callback(error_msg, 0)
        raise FileNotFoundError(error_msg)

    with open(os.path.join(workingDir, "metadata", cover[0]), "rb") as f:
        coverBytes = f.read()
    coverMime = mimetypes.guess_type(cover[0])[0]

    # Open JSON file with UTF-8 encoding
    with open(os.path.join(workingDir, "metadata", "metadata.json"), "r", encoding="utf-8") as f:
        metadata = json.load(f)

    authorName = "Unknown"
    for creator in metadata["creator"]:
        if "author" in creator["role"]:
            authorName = creator["name"]

    chapters = {}
    for chap in metadata["chapters"]:
        chapters.setdefault(chap["spine"], []).append(chap)

    # Collect all parts to process
    parts = [file for file in workingList if file.startswith("Part ")]
    total = len(parts)
    if total == 0:
        error_msg = "ERROR: No parts found to process."
        if progress_callback:
            progress_callback(error_msg, 0)
        raise FileNotFoundError(error_msg)

    for index, file in enumerate(parts):
        number = file[len("Part "):].split(".")[0]
        spine_index = int(number) - 1

        audiofile = eyed3.load(os.path.join(workingDir, file))
        if audiofile.tag is None:
            # explizit ID3v2.4 initialisieren (UTF-8)
            audiofile.initTag(version=ID3_V2_4)
        else:
            audiofile.tag.clear()

        # make that we work with V2.4 and UTF-8
        audiofile.tag.version = ID3_V2_4

        audiofile.tag.title = f"Part {int(number)}"
        audiofile.tag.artist = authorName
        audiofile.tag.images.set(3, coverBytes, coverMime)
        audiofile.tag.album = metadata["title"]
        audiofile.tag.track_num = (int(number), len(metadata["spine"]))

        # Get chapters for this spine index
        spine_chapters = chapters.get(spine_index, [])
        if spine_chapters:
            # Check for non-increasing offsets
            prev_offset = spine_chapters[0]["offset"]
            for i,chap in enumerate(spine_chapters[1:], start=1):
                current_offset = chap["offset"]
                if current_offset <= prev_offset:
                    # Found overlapping chapter - report and exit
                    error_parts = [
                        f"ERROR: {os.path.join(workingDir, 'metadata', 'metadata.json')} has errors with overlapping chapter times.",
                        f"Look in chapters for spine: {spine_index}",
                        f"Chapter '{spine_chapters[i-1]['title']}' at offset: {spine_chapters[i-1]['offset']}",
                        f"Chapter '{chap['title']}' at offset: {current_offset}"
                    ]

                    # Format for current mode
                    if progress_callback and hasattr(progress_callback, '__self__'):
                        error_msg = "<br>".join(error_parts)
                    else:
                        error_msg = "\n".join(error_parts)

                    # Only send via exception, not progress callback
                    raise ValueError(error_msg)
                prev_offset = current_offset

        # Process chapters normally since offsets are valid
        last = None
        child_ids = []

        for i, chap in enumerate(chapters.get(int(number) - 1, [])):
            if last is None:
                last = chap
                continue
            cid = f"ch{i}".encode("ascii")
            child_ids.append(cid)
            c = audiofile.tag.chapters.set(
                cid,
                (int(last["offset"]) * 1000, int(chap["offset"]) * 1000 - 1)
            )
            c.title = last["title"]
            last = chap

        if last is not None:
            c = audiofile.tag.chapters.set(
                b"last",
                (
                    int(last["offset"]) * 1000,
                    int(metadata["spine"][chap["spine"]]["duration"] * 1000)
                )
            )
            c.title = last["title"]

        audiofile.tag.table_of_contents.set(
            b"toc",
            toplevel=True,
            child_ids=child_ids + [b"last"],
            description="Table of Contents"
        )

        # als v2.4 speichern, damit UTF-8 Zeichen (Umlaute) korrekt sind
        audiofile.tag.save(version=ID3_V2_4)

        # Update progress
        if progress_callback:
            progress = int((index + 1) * 100 / total)
            progress_callback(f"Baked: {file}", progress)

# -------- MAIN ENTRY POINT --------

def main():
    parser = argparse.ArgumentParser(description="Bake audiobook metadata.")
    parser.add_argument("directory", nargs="?", default=None, help="Path to audiobook directory")
    args = parser.parse_args()

    def cli_callback(message, progress):
        # Only display non-error messages here
        if not message.startswith("ERROR"):
            print(f"{message} ({progress}%)")

    if args.directory:
        workingDir = args.directory
    else:
        workingDir = input("Path to audiobook dir: ").strip()

    try:
        bake_metadata(workingDir, progress_callback=cli_callback)
    except Exception as e:
        print(f"\033[91m{e}\033[0m")
        sys.exit(1)

if __name__ == "__main__":
    main()
