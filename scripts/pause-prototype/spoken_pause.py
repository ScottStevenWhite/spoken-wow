#!/usr/bin/env python3
"""Try the pause-by-sentence prototype of Spoken on your own WoW Forever install.

    python spoken_pause.py              # shows what is installed and asks what to do
    python spoken_pause.py install      # back up, convert your Spoken voice packs, install the prototype
    python spoken_pause.py restore      # put everything back exactly as it was
    python spoken_pause.py status

Needs Python 3.8 or newer and ffmpeg. Close WoW first. Works on Windows, macOS and Linux.

Your Spoken voice packs are converted on your own computer: the audio is never downloaded from
anywhere but where you got Spoken. The originals are moved, never deleted, to a folder beside
AddOns (Interface/SpokenPausePrototype), and `restore` moves them back.
"""
import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

PROTOTYPE_VERSION = "0.1.0"
#: The Spoken release the prototype's addon code is built on.
BASE_VERSION = "3.8.3"
#: Spoken's addon folders the prototype replaces whole, so every file matches.
CODE_FOLDERS = ("Spoken", "Spoken_Quests", "Spoken_Places", "Spoken_Readables", "Spoken_Bosses")
#: Written into each code folder the prototype installs, so restore removes only its own.
CODE_MARKER = ".spoken-pause-prototype"
STATE_DIR_NAME = "SpokenPausePrototype"
PACK_NAME = re.compile(r"^Spoken.*Audio")

HERE = Path(__file__).resolve().parent
if (HERE / "addons").is_dir():             # the release zip
    CODE_SOURCE = HERE / "addons"
    CONVERTER = HERE / "converter"
else:                                       # a checkout of the repository
    CODE_SOURCE = HERE.parent.parent / "addons"
    CONVERTER = HERE.parent.parent / "pipelines" / "quests"
sys.path.insert(0, str(CONVERTER))

from tts_cli import pieces  # noqa: E402

SYSTEM = platform.system()


class Problem(Exception):
    """Something the player has to fix; printed without a traceback."""


def say(text=""):
    print(text, flush=True)


# ---------------------------------------------------------------- finding things

def candidate_addons():
    """Where WoW Forever's AddOns folder usually is on this kind of computer."""
    home = Path.home()
    found = []
    if SYSTEM == "Windows":
        roots = []
        try:
            import winreg
            for hive, key in ((winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Blizzard Entertainment\World of Warcraft"),
                              (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Blizzard Entertainment\World of Warcraft")):
                try:
                    with winreg.OpenKey(hive, key) as handle:
                        install = Path(winreg.QueryValueEx(handle, "InstallPath")[0])
                        # InstallPath names a flavour's folder (_retail_, _classic_): the game's is its parent.
                        roots.append(install.parent if install.name.startswith("_") else install)
                except OSError:
                    pass
        except ImportError:
            pass
        for drive in "CDEFGH":
            for folder in (r"Program Files (x86)\World of Warcraft", r"Program Files\World of Warcraft",
                           r"World of Warcraft", r"Games\World of Warcraft"):
                roots.append(Path(f"{drive}:\\") / folder)
        found = [root / "_forever_" / "Interface" / "AddOns" for root in roots]
    elif SYSTEM == "Darwin":
        found = [Path("/Applications/World of Warcraft/_forever_/Interface/AddOns"),
                 home / "Applications/World of Warcraft/_forever_/Interface/AddOns"]
    else:
        games = home / "Games"
        found = [games / "battlenet/drive_c/Program Files (x86)/World of Warcraft/_forever_/Interface/AddOns"]
        if games.is_dir():
            for prefix in games.iterdir():
                found.append(prefix / "drive_c/Program Files (x86)/World of Warcraft/_forever_/Interface/AddOns")
                found.append(prefix / "World of Warcraft/_forever_/Interface/AddOns")
    unique = []
    for path in found:
        if path.is_dir() and path.resolve() not in [p.resolve() for p in unique]:
            unique.append(path)
    return unique


def find_addons(given):
    if given:
        path = Path(given).expanduser()
        if not path.is_dir():
            raise Problem(f"There is no folder at {path}")
        return path
    found = candidate_addons()
    if not found:
        raise Problem("Couldn't find WoW Forever's AddOns folder. Give it with --addons, e.g.\n"
                      '  python spoken_pause.py install --addons "D:\\Games\\World of Warcraft\\_forever_\\Interface\\AddOns"')
    if len(found) > 1:
        listed = "\n".join(f"  {p}" for p in found)
        raise Problem(f"Found more than one AddOns folder; choose one with --addons:\n{listed}")
    return found[0]


def wow_running():
    """Whether WoW Forever is open. A check that cannot run is not a reason to stop."""
    try:
        if SYSTEM == "Windows":
            out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq Wow.exe"], capture_output=True, text=True).stdout
            return "wow.exe" in out.lower()
        pattern = r"_forever_/.*\.app/Contents/MacOS" if SYSTEM == "Darwin" else r"Wow\.exe"
        return subprocess.run(["pgrep", "-if", pattern], capture_output=True).returncode == 0
    except OSError:
        return False


def check_ffmpeg():
    if shutil.which("ffmpeg") and shutil.which("ffprobe"):
        return
    how = {
        "Windows": "  winget install Gyan.FFmpeg\nthen close this window and open a new one.",
        "Darwin": "  brew install ffmpeg\n(Homebrew comes from https://brew.sh)",
    }.get(SYSTEM, "  sudo apt install ffmpeg   (or your distribution's package)")
    raise Problem("ffmpeg isn't installed. Install it with:\n" + how)


def toc_version(folder):
    toc = folder / f"{folder.name}.toc"
    if not toc.is_file():
        return None
    match = re.search(r"^## Version:\s*(\S+)", toc.read_text(encoding="utf-8", errors="replace"), re.M)
    return match.group(1) if match else None


def version_tuple(text):
    return tuple(int(part) for part in re.findall(r"\d+", text or "")[:3])


def is_converted(pack):
    toc = pack / f"{pack.name}.toc"
    text = toc.read_text(encoding="utf-8", errors="replace") if toc.is_file() else ""
    return pieces.TOC_MARKER in text or pieces.LOOKUP_TOC_MARKER in text


def voice_packs(addons):
    return sorted(p for p in addons.iterdir()
                  if p.is_dir() and PACK_NAME.match(p.name) and (p / f"{p.name}.toc").is_file())


def folder_size(path):
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


# ---------------------------------------------------------------- state

def state_dir(addons):
    # Beside AddOns, never in it (WoW would try to load what is there), and on the same drive, so
    # moving 2-3 GB of packs in and out is a rename rather than a copy.
    return addons.parent / STATE_DIR_NAME


def load_state(addons):
    path = state_dir(addons) / "state.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else None


def save_state(addons, state):
    path = state_dir(addons) / "state.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")


def keep_own_audio(original, target):
    """Copies the sound files the player's own install has and the download lacks. The download
    carries no audio at all (THIRD_PARTY.md), not even an addon's own clips, such as an easter egg."""
    if not original.is_dir():
        return
    for path in original.rglob("*"):
        if path.is_file() and path.suffix.lower() in (".ogg", ".mp3", ".wav"):
            destination = target / path.relative_to(original)
            if not destination.exists():
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, destination)


# ---------------------------------------------------------------- commands

def status(addons):
    state = load_state(addons)
    say(f"AddOns folder: {addons}")
    say(f"Spoken installed: {toc_version(addons / 'Spoken') or 'no'}")
    say(f"Prototype: {'INSTALLED, version ' + state['version'] if state else 'not installed'}")
    for pack in voice_packs(addons):
        say(f"  {pack.name}: {'sentence pieces' if is_converted(pack) else 'original'}")
    if state:
        missing = [name for name in state["code"] if not (addons / name / CODE_MARKER).is_file()]
        if missing:
            say("\nWarning: Spoken seems to have been updated since the prototype was installed "
                f"({', '.join(missing)}). Run restore, then install again.")


def install(addons, args):
    if load_state(addons):
        raise Problem("The prototype is already installed. To reinstall: python spoken_pause.py update")
    installed = toc_version(addons / "Spoken")
    if not installed:
        raise Problem("Spoken isn't installed in this AddOns folder. Install it and its voice packs "
                      "with Spoken Manager or CurseForge first.")
    if version_tuple(installed) > version_tuple(BASE_VERSION) and not args.force:
        raise Problem(f"Your Spoken ({installed}) is newer than the prototype's ({BASE_VERSION}). Installing would "
                      "put an older Spoken in its place. Wait for a newer prototype, or add --force to try anyway.")
    packs = voice_packs(addons)
    if any(is_converted(p) for p in packs):
        raise Problem("Some voice packs are already converted but the prototype's records are missing. "
                      "Reinstall those packs with Spoken Manager or CurseForge first.")
    if not packs:
        raise Problem("No Spoken voice packs found. Install them with Spoken Manager or CurseForge first.")
    check_ffmpeg()

    need = sum(folder_size(p) for p in packs) * 1.15
    free = shutil.disk_usage(addons).free
    if free < need:
        raise Problem(f"Not enough free space: about {need / 1e9:.1f} GB is needed while converting, "
                      f"{free / 1e9:.1f} GB is free.")

    root = state_dir(addons)
    staging = root / "staging"
    if staging.exists():
        shutil.rmtree(staging)             # only ever our own half-finished conversion
    staging.mkdir(parents=True)

    say(f"Converting {len(packs)} voice packs into sentence pieces. This takes a while (10-30 minutes).")
    converted, skipped = [], []
    started = time.time()
    for pack in packs:
        def progress(done, total, name=pack.name):
            if done % 200 == 0 or done == total:
                print(f"\r  {name}: {done}/{total}", end="", flush=True)
        try:
            pieces.convert_pack(str(pack), str(staging), progress=progress)
            print()
            converted.append(pack.name)
        except ValueError as error:
            print()
            say(f"  {pack.name}: left as it is ({error})")
            skipped.append(pack.name)
    say(f"Converted in {int(time.time() - started) // 60} min {int(time.time() - started) % 60} s.")

    # Swapped only once everything is converted, and recorded as it goes, so an interruption can
    # still be restored.
    state = {"version": PROTOTYPE_VERSION, "base": BASE_VERSION, "spoken_before": installed,
             "installed_at": time.strftime("%Y-%m-%d %H:%M"), "code": [], "packs": [], "added_code": []}
    backup = root / "backup"
    (backup / "code").mkdir(parents=True, exist_ok=True)
    (backup / "packs").mkdir(parents=True, exist_ok=True)
    save_state(addons, state)
    for name in CODE_FOLDERS:
        source = CODE_SOURCE / name
        if not source.is_dir():
            continue
        target = addons / name
        if target.exists():
            shutil.move(str(target), str(backup / "code" / name))
            state["code"].append(name)
        else:
            state["added_code"].append(name)
        save_state(addons, state)
        shutil.copytree(source, target, ignore=shutil.ignore_patterns(".DS_Store", "*.bak", "*.orig"))
        keep_own_audio(backup / "code" / name, target)
        (target / CODE_MARKER).write_text(PROTOTYPE_VERSION, encoding="utf-8")
    for name in converted:
        shutil.move(str(addons / name), str(backup / "packs" / name))
        state["packs"].append(name)
        save_state(addons, state)
        shutil.move(str(staging / name), str(addons / name))
    shutil.rmtree(staging, ignore_errors=True)

    say("\nDone. Start WoW and try it:")
    say("  - Pause (two bars) / Play: starts the current sentence again")
    say("  - Stop (square) / Play: goes back to the start of the text on screen")
    say("  - Stop / Replay (circle arrow): starts the whole line again")
    say("\nWhile the prototype is in, don't update Spoken or its packs (turn off automatic updates in")
    say("Spoken Manager or CurseForge). To undo everything: python spoken_pause.py restore")


def restore(addons):
    state = load_state(addons)
    if not state:
        raise Problem("The prototype isn't installed here; there is nothing to restore.")
    root = state_dir(addons)
    backup = root / "backup"
    # Everything is checked before anything moves, so a problem leaves AddOns as it was.
    for name in state["packs"]:
        current = addons / name
        if current.exists() and not is_converted(current):
            raise Problem(f"{name} in AddOns isn't the prototype's converted pack (was it updated?). Nothing "
                          f"was changed. The original is safe in {backup / 'packs' / name}.")
        if not (backup / "packs" / name).exists():
            raise Problem(f"The backup of {name} is missing from {backup / 'packs'}. Nothing was changed.")
    for name in state["code"] + state.get("added_code", []):
        current = addons / name
        if current.exists() and not (current / CODE_MARKER).is_file():
            raise Problem(f"{name} in AddOns isn't the prototype's (was Spoken updated?). Nothing was "
                          f"changed. The original is safe in {backup / 'code' / name}.")
        if name in state["code"] and not (backup / "code" / name).exists():
            raise Problem(f"The backup of {name} is missing from {backup / 'code'}. Nothing was changed.")
    for name in state["packs"]:
        current = addons / name
        if current.exists():
            shutil.rmtree(current)
        shutil.move(str(backup / "packs" / name), str(current))
    for name in state["code"] + state.get("added_code", []):
        current = addons / name
        if current.exists():
            shutil.rmtree(current)
        if name in state["code"]:
            shutil.move(str(backup / "code" / name), str(current))
    shutil.rmtree(root)
    say("Restored: your original Spoken and voice packs are back.")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("command", nargs="?", choices=("install", "restore", "update", "status"))
    parser.add_argument("--addons", help="WoW Forever's Interface/AddOns folder, if it isn't found by itself")
    parser.add_argument("--force", action="store_true", help="install over a newer Spoken")
    parser.add_argument("--skip-wow-check", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--code-source", help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if args.code_source:
        global CODE_SOURCE
        CODE_SOURCE = Path(args.code_source)

    try:
        addons = find_addons(args.addons)
        command = args.command
        if not command:
            status(addons)
            say()
            choice = input("Type install, restore, or press Enter to quit: ").strip().lower()
            if choice not in ("install", "restore"):
                return 0
            command = choice
        if command != "status" and not args.skip_wow_check and wow_running():
            raise Problem("Close WoW first: it only notices new files when it starts.")
        if command == "status":
            status(addons)
        elif command == "install":
            install(addons, args)
        elif command == "restore":
            restore(addons)
        elif command == "update":
            if load_state(addons):
                restore(addons)
            install(addons, args)
        return 0
    except Problem as problem:
        say(f"\n{problem}")
        return 1
    except KeyboardInterrupt:
        say("\nStopped. If it stopped while converting, AddOns is unchanged. If it stopped while swapping")
        say("folders, run: python spoken_pause.py restore")
        return 1


if __name__ == "__main__":
    sys.exit(main())
