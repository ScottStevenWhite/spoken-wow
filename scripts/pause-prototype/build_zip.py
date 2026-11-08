#!/usr/bin/env python3
"""Builds the prototype's download: the tool, Spoken's patched addon folders and the converter.

    python scripts/pause-prototype/build_zip.py        # writes dist/spoken-pause-prototype-<version>.zip

No audio goes in it: each player's own voice packs are converted on their own computer, so
nothing of Spoken's recordings is ever redistributed.
"""
import os
import sys
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
sys.path.insert(0, str(HERE))
import spoken_pause  # noqa: E402

TOP = "spoken-pause-prototype"
SKIP = {".DS_Store"}
SKIP_SUFFIXES = (".bak", ".orig", ".pyc")
EXECUTABLE = {"spoken_pause.py", "try-it-mac.command"}
AUDIO = (".ogg", ".mp3", ".wav")

NOTICE = f"""Spoken pause-by-sentence prototype {spoken_pause.PROTOTYPE_VERSION}

An unofficial test build of Spoken (https://github.com/rusty-key/spoken-wow), based on Spoken
{spoken_pause.BASE_VERSION}, with a Pause that resumes from the current sentence. It has been
proposed to Spoken's developers but isn't part of Spoken.

Spoken's code is MIT-licensed (see LICENSE); this build keeps that license. It contains no audio:
the tool converts the voice packs you installed yourself, on your own computer.

Start with TRY-IT.md.
"""


def add_file(archive, source, name):
    if source.suffix.lower() in AUDIO:
        raise SystemExit(f"refusing to package audio: {source}")
    info = zipfile.ZipInfo.from_file(source, f"{TOP}/{name}")
    # Executable where a Mac or Linux needs it to be double-clickable or runnable.
    mode = 0o755 if source.name in EXECUTABLE else 0o644
    info.external_attr = (0o100000 | mode) << 16
    info.compress_type = zipfile.ZIP_DEFLATED
    with open(source, "rb") as f:
        data = f.read()
    if source.suffix == ".bat":
        # cmd.exe misreads a batch file with bare LF line ends, and git may have stored it that way.
        data = data.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
    archive.writestr(info, data)


def main():
    dist = REPO / "dist"
    dist.mkdir(exist_ok=True)
    target = dist / f"{TOP}-{spoken_pause.PROTOTYPE_VERSION}.zip"
    count = 0
    with zipfile.ZipFile(target, "w") as archive:
        for name in ("spoken_pause.py", "try-it-windows.bat", "try-it-mac.command", "TRY-IT.md"):
            add_file(archive, HERE / name, name)
            count += 1
        add_file(archive, REPO / "LICENSE", "LICENSE")
        archive.writestr(f"{TOP}/NOTICE.txt", NOTICE)
        for name in ("pieces.py", "length_table.py", "store.py"):
            add_file(archive, REPO / "pipelines" / "quests" / "tts_cli" / name, f"converter/tts_cli/{name}")
            count += 1
        add_file(archive, REPO / "THIRD_PARTY.md", "THIRD_PARTY.md")
        left_out = []
        for folder in spoken_pause.CODE_FOLDERS:
            root = REPO / "addons" / folder
            for path in sorted(root.rglob("*")):
                if not path.is_file() or path.name in SKIP or path.name.endswith(SKIP_SUFFIXES):
                    continue
                # Audio is never shipped, not even the addons' own clips (THIRD_PARTY.md): the tool
                # copies each player's own copy into place instead.
                if path.suffix.lower() in AUDIO:
                    left_out.append(path.relative_to(REPO).as_posix())
                    continue
                add_file(archive, path, f"addons/{folder}/{path.relative_to(root).as_posix()}")
                count += 1
    for name in left_out:
        print(f"left out (copied from the player's own install): {name}")
    print(f"{target} ({count + 3} files, {os.path.getsize(target) / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
