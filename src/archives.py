import os
import re
import shutil
import subprocess
import zipfile
from enum import Enum
from functools import lru_cache

# Candidate binary names for a 7-Zip CLI, in preference order: "7zz" is what
# Homebrew's sevenzip formula installs; "7z"/"7za" are the common names from
# p7zip, apt/dnf packages, and the official Windows installer.
SEVEN_ZIP_BINARY_NAMES = ("7zz", "7z", "7za")

ARCHIVE_EXTENSIONS = (".7z", ".zip")

# System junk that comes along with files: it is cleaned after processing, and doesn't count as archive contents
META_FILES = ("desktop.ini", "thumbs.db", ".ds_store")
META_FOLDERS = ("__macosx",)

# Names that tell nothing about the game, as disc-based dumps often have: "game.iso", "Disc 1.cue",
# "CD2.bin", "track01.bin" (Dreamcast GDI, cue/bin), "disk1.adf", "Disk 1 Side A.st" (floppies),
# "EBOOT.BIN" (PS3), "default.xbe" (Xbox), "boot.dol"/"main.dol" (GameCube, Wii).
# Such a name is made of these words only, each one can be numbered ("disc2", "Disk 1A", "Side B", "Disc 1 of 2").
# A bare number counts too, if it's short ("01.bin"), so "1942.nes" is still a game.
GENERIC_WORDS = ("game", "rom", "image", "img", "iso", "disc", "disk", "cd", "cdrom", "dvd", "gd", "gdrom", "umd",
                 "floppy", "tape", "side", "track", "data", "default", "boot", "eboot", "main", "of")
GENERIC_NUMBER_LENGTH = 2

# A short extension, without spaces, so "Vol. 1 (USA)" is not taken for one
_EXTENSION = re.compile(r"\.[a-z0-9]{1,5}", re.IGNORECASE)

class ExtractMode(Enum):
    PLAIN = 1    # the contents go next to the archive
    FOLDERS = 2  # every archive gets its own folder
    AUTO = 3     # own folder only when the plain extraction would be a mess (see needs_own_folder)

@lru_cache(maxsize=None)
def find_seven_zip_binary():
    """Locate a usable 7-Zip CLI binary on PATH, or None if none is installed."""
    for name in SEVEN_ZIP_BINARY_NAMES:
        path = shutil.which(name)
        if path:
            return path
    return None

def is_archive(file_name) -> bool:
    return file_name.lower().endswith(ARCHIVE_EXTENSIONS)

def strip_extensions(name) -> str:
    """The name without its extensions: "game.nkit.iso" -> "game"."""
    stem, extension = os.path.splitext(name)
    while stem and _EXTENSION.fullmatch(extension):
        name = stem
        stem, extension = os.path.splitext(name)
    return name

def is_generic_name(name) -> bool:
    """Is the file (or folder) name telling nothing about the game, like "Disc 1.iso" or "track01.bin"."""
    stem = strip_extensions(name).lower()
    if not re.fullmatch(r"[a-z0-9\s._-]+", stem):
        return False
    previous = None
    for token in re.findall(r"[a-z]+|\d+", stem):
        is_number = token.isdigit() and (previous is not None or len(token) <= GENERIC_NUMBER_LENGTH)
        is_letter = len(token) == 1 and previous is not None
        if not (is_number or is_letter or token in GENERIC_WORDS):
            return False
        previous = token
    return previous is not None

def list_entries(file_name) -> list[str]:
    """Paths of everything inside the archive, with '/' separators."""
    if file_name.lower().endswith(".zip"):
        with zipfile.ZipFile(file_name, 'r') as archive:
            return archive.namelist()
    # The technical listing has one "Path = ..." line per entry, after the archive's own block ending with dashes
    result = subprocess.run([find_seven_zip_binary(), "l", "-slt", os.path.abspath(file_name)],
                            check=True, capture_output=True)
    _, _, entries = result.stdout.decode(errors="replace").partition("\n----------")
    return [line[len("Path = "):].replace("\\", "/") for line in entries.splitlines() if line.startswith("Path = ")]

def top_level_entries(entries) -> set[str]:
    """Names of the files and folders that land right in the target folder, without the system junk."""
    names = set()
    for entry in entries:
        parts = [part for part in entry.split("/") if part not in ("", ".")]
        if parts and parts[0].lower() not in META_FILES + META_FOLDERS:
            names.add(parts[0])
    return names

def needs_own_folder(top_level) -> bool:
    """An archive with a few things inside, or one with a generic name, would clutter the folder it's extracted to."""
    return len(top_level) > 1 or any(is_generic_name(name) for name in top_level)

def own_folder_name(file_name, top_level) -> str:
    """The archive name without its extension, and without the inner file's extension too, if romlm packed it."""
    name = os.path.splitext(os.path.basename(file_name))[0]
    if name in top_level:
        name = os.path.splitext(name)[0] or name
    return name

def extraction_folder(file_name, target_folder, mode) -> str:
    """Where the archive's contents should go, according to the mode. AUTO mode reads the archive to decide."""
    if mode == ExtractMode.PLAIN:
        return target_folder
    top_level = top_level_entries(list_entries(file_name))
    if mode == ExtractMode.AUTO and not needs_own_folder(top_level):
        return target_folder
    return os.path.join(target_folder, own_folder_name(file_name, top_level))

def unpack(file_name, target_folder):
    """Extracts the archive into the folder, and removes the archive."""
    if file_name.lower().endswith(".7z"):
        subprocess.run(
            [find_seven_zip_binary(), "x", os.path.abspath(file_name), f"-o{os.path.abspath(target_folder)}", "-y"],
            check=True, capture_output=True,
        )
    elif file_name.lower().endswith(".zip"):
        with zipfile.ZipFile(file_name, 'r') as archive:
            archive.extractall(target_folder)
    os.remove(file_name)

def pack(file_name, target_folder, packing_format) -> str:
    """Packs the file into an archive in the folder, and removes the file. Returns the archive path."""
    archive_file = f"{os.path.join(target_folder, os.path.basename(file_name))}.{packing_format}"
    try:
        if packing_format == "7z":
            # Run with cwd set to the source file's folder, passing only its basename,
            # so the archive stores just that name (matching the old arcname behavior)
            # instead of the full source path.
            subprocess.run(
                [find_seven_zip_binary(), "a", os.path.abspath(archive_file), os.path.basename(file_name)],
                cwd=os.path.dirname(os.path.abspath(file_name)),
                check=True, capture_output=True,
            )
        elif packing_format == "zip":
            with zipfile.ZipFile(archive_file, 'w', zipfile.ZIP_DEFLATED) as archive:
                archive.write(file_name, arcname=os.path.basename(file_name))
    except Exception:
        # Don't leave a half-written archive next to the source file
        if os.path.exists(archive_file):
            os.remove(archive_file)
        raise
    os.remove(file_name)
    return archive_file

def describe_error(error) -> str:
    """A one-line reason of why an archive could not be processed."""
    if isinstance(error, subprocess.CalledProcessError):
        output = error.stderr or error.stdout or b""
        details = output.decode(errors="replace").strip().splitlines()
        return f"7-Zip failed with code {error.returncode}" + (f": {details[-1]}" if details else "")
    return f"{type(error).__name__}: {error}"
