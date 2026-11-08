"""The prototype's installer: converts the packs, swaps the code in, and restores exactly."""
import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import spoken_pause  # noqa: E402

pytestmark = pytest.mark.skipif(not (shutil.which("ffmpeg") and shutil.which("ffprobe")),
                                reason="needs ffmpeg and ffprobe")


def speech(path, parts, codec=("-c:a", "libvorbis", "-q:a", "0")):
    inputs, labels = [], []
    for i, (kind, seconds) in enumerate(parts):
        source = f"sine=frequency=220:sample_rate=44100:duration={seconds}" if kind == "tone" \
            else f"anullsrc=r=44100:cl=mono:d={seconds}"
        inputs += ["-f", "lavfi", "-i", source]
        labels.append(f"[{i}:a]")
    graph = "".join(labels) + f"concat=n={len(parts)}:v=0:a=1,aformat=channel_layouts=mono[out]"
    subprocess.run(["ffmpeg", "-v", "error", "-y", *inputs, "-filter_complex", graph, "-map", "[out]",
                    *codec, str(path)], check=True)


THREE = [("tone", 3.0), ("quiet", 0.6), ("tone", 2.5), ("quiet", 0.6), ("tone", 3.0)]


def digest(root):
    h = hashlib.sha256()
    for folder, _, files in sorted(os.walk(root)):
        for name in sorted(files):
            path = os.path.join(folder, name)
            h.update(os.path.relpath(path, root).encode())
            with open(path, "rb") as f:
                h.update(f.read())
    return h.hexdigest()


@pytest.fixture
def world(tmp_path):
    addons = tmp_path / "_forever_" / "Interface" / "AddOns"
    for name in ("Spoken", "Spoken_Quests"):
        (addons / name).mkdir(parents=True)
        (addons / name / f"{name}.toc").write_text(f"## Version: 3.8.3\n## Title: {name}\n")
        (addons / name / "Core.lua").write_text("-- the release\n")
    (addons / "OtherAddon").mkdir()
    (addons / "OtherAddon" / "OtherAddon.toc").write_text("## Title: other\n")

    quests = addons / "SpokenQuestsAudioAlliance"
    (quests / "generated" / "sounds" / "quests").mkdir(parents=True)
    (quests / "SpokenQuestsAudioAlliance.toc").write_text("## Title: q\n\ngenerated\\sound_length_table.lua\n")
    (quests / "generated" / "sound_length_table.lua").write_text("-- lengths\n")
    speech(quests / "generated" / "sounds" / "quests" / "1-accept.ogg", THREE)

    places = addons / "SpokenPlacesAudio"
    (places / "Data").mkdir(parents=True)
    (places / "Sounds" / "12").mkdir(parents=True)
    (places / "SpokenPlacesAudio.toc").write_text("## Title: p\n\nData/Sounds.lua\n")
    (places / "Data" / "Sounds.lua").write_text('local pack = { zones = { [12] = { file = "12\\\\zone", len = 9.7 } } }\n')
    speech(places / "Sounds" / "12" / "zone.mp3", THREE, ("-c:a", "libmp3lame", "-b:a", "128k"))

    code = tmp_path / "prototype-addons"
    for name in spoken_pause.CODE_FOLDERS:
        (code / name).mkdir(parents=True)
        (code / name / f"{name}.toc").write_text(f"## Version: 3.8.3\n## Title: {name} prototype\n")
        (code / name / "Core.lua").write_text("-- the prototype\n")
    return addons, code


def run(addons, code, *command):
    return spoken_pause.main([*command, "--addons", str(addons), "--skip-wow-check", "--code-source", str(code)])


def test_install_converts_the_packs_and_swaps_the_code_in(world):
    addons, code = world
    assert run(addons, code, "install") == 0
    assert spoken_pause.is_converted(addons / "SpokenQuestsAudioAlliance")
    assert spoken_pause.is_converted(addons / "SpokenPlacesAudio")
    assert (addons / "SpokenQuestsAudioAlliance" / "generated" / "sounds" / "quests" / "1-accept" / "01.ogg").is_file()
    assert (addons / "SpokenPlacesAudio" / "Sounds" / "12" / "zone" / "01.mp3").is_file()
    for name in spoken_pause.CODE_FOLDERS:
        assert (addons / name / "Core.lua").read_text() == "-- the prototype\n"
        assert (addons / name / spoken_pause.CODE_MARKER).is_file()
    assert (addons / "OtherAddon" / "OtherAddon.toc").is_file()
    state = spoken_pause.load_state(addons)
    assert state["code"] == ["Spoken", "Spoken_Quests"]
    assert sorted(state["added_code"]) == ["Spoken_Bosses", "Spoken_Places", "Spoken_Readables"]
    assert sorted(state["packs"]) == ["SpokenPlacesAudio", "SpokenQuestsAudioAlliance"]
    # Kept beside AddOns, never inside it, where the game would try to load it.
    assert not any(p.name == spoken_pause.STATE_DIR_NAME for p in addons.iterdir())


def test_restore_puts_back_exactly_what_was_there(world):
    addons, code = world
    before = digest(addons)
    run(addons, code, "install")
    assert run(addons, code, "restore") == 0
    assert digest(addons) == before
    assert not spoken_pause.state_dir(addons).exists()


def test_update_reinstalls_over_an_installed_prototype(world):
    addons, code = world
    before = digest(addons)
    run(addons, code, "install")
    assert run(addons, code, "update") == 0
    assert spoken_pause.is_converted(addons / "SpokenQuestsAudioAlliance")
    run(addons, code, "restore")
    assert digest(addons) == before


def test_a_second_install_is_refused(world, capsys):
    addons, code = world
    run(addons, code, "install")
    assert run(addons, code, "install") == 1
    assert "already installed" in capsys.readouterr().out


def test_a_newer_spoken_is_not_replaced_without_force(world, capsys):
    addons, code = world
    (addons / "Spoken" / "Spoken.toc").write_text("## Version: 3.9.0\n")
    assert run(addons, code, "install") == 1
    assert "newer than the prototype" in capsys.readouterr().out
    assert not spoken_pause.state_dir(addons).exists()
    assert run(addons, code, "install", "--force") == 0


def test_a_pack_it_cannot_read_is_left_as_it_is(world):
    addons, code = world
    odd = addons / "SpokenOddAudio"
    odd.mkdir()
    (odd / "SpokenOddAudio.toc").write_text("## Title: odd\n")
    run(addons, code, "install")
    assert (addons / "SpokenOddAudio" / "SpokenOddAudio.toc").is_file()
    assert "SpokenOddAudio" not in spoken_pause.load_state(addons)["packs"]


def test_restore_never_removes_a_folder_that_is_not_the_prototypes(world, capsys):
    addons, code = world
    run(addons, code, "install")
    (addons / "Spoken" / spoken_pause.CODE_MARKER).unlink()     # as if Spoken updated itself
    packs_before = digest(addons / "SpokenQuestsAudioAlliance")
    assert run(addons, code, "restore") == 1
    assert "isn't the prototype's" in capsys.readouterr().out
    assert (addons / "Spoken" / "Core.lua").is_file()
    # Checked before anything moved: the packs are still the converted ones.
    assert digest(addons / "SpokenQuestsAudioAlliance") == packs_before


def test_the_players_own_addon_audio_is_kept(world):
    addons, code = world
    (addons / "Spoken_Quests" / "Sounds").mkdir()
    (addons / "Spoken_Quests" / "Sounds" / "og-thrall.mp3").write_bytes(b"their own clip")
    run(addons, code, "install")
    assert (addons / "Spoken_Quests" / "Sounds" / "og-thrall.mp3").read_bytes() == b"their own clip"
