import os
import shutil
import subprocess
import zipfile
from functools import lru_cache

# Candidate binary names for a 7-Zip CLI, in preference order: "7zz" is what
# Homebrew's sevenzip formula installs; "7z"/"7za" are the common names from
# p7zip, apt/dnf packages, and the official Windows installer.
SEVEN_ZIP_BINARY_NAMES = ("7zz", "7z", "7za")

ARCHIVE_EXTENSIONS = (".7z", ".zip")

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
