import os
import re

import archives
from tags import get_base_name, strip_tags

# Sheets that describe a disc image and come along with its data files: ".cue" (with ".bin", ".iso", ".img" or
# ".wav" tracks), ".gdi" (Dreamcast, with ".bin" and ".raw" tracks), ".ccd" (CloneCD, with ".img" and ".sub"),
# ".mds" (Alcohol 120%, with ".mdf") and ".toc" (cdrdao, with ".bin"). Also ".m3u" playlists of multi-disc games.
SHEET_EXTENSIONS = (".cue", ".gdi", ".ccd", ".mds", ".toc", ".m3u")

# Playlists are often named on their own ("FF7.m3u"), so they don't tell which game the folder holds
PLAYLIST_EXTENSIONS = (".m3u",)

# Files and folders at the root of an extracted disc: PS3 ("PS3_DISC.SFB", "PS3_GAME"), PSP ("UMD_DATA.BIN",
# "PSP_GAME"), PS1 and PS2 ("SYSTEM.CNF"), Xbox ("default.xbe") and Xbox 360 ("default.xex"). Such a folder
# is a game of its own, whatever the names inside are.
DISC_ROOT_FILES = ("ps3_disc.sfb", "umd_data.bin", "system.cnf", "default.xbe", "default.xex")
DISC_ROOT_FOLDERS = ("ps3_game", "psp_game")

# The folders of --sort: lettered ones ("A", "1-9"), and the special ones ("!!BIOS", "!Homebrew", "!Japan")
SORT_FOLDER = re.compile(r"[a-z]|1-9|!.*", re.IGNORECASE)

def _is_of_one_game(folder_name, file_names, folder_names) -> bool:
    """
    Are all the files (but the generic named ones, like "track01.bin") of the game the folder is named after,
    or of one game at all ("FF7/Final Fantasy VII (USA).cue"), if the folder has nothing else inside, and it's not
    a --sort folder, that can hold a single game just by chance ("Q/Quake (USA).cue").
    """
    games = {get_base_name(name).lower() for name in file_names
             if not name.lower().endswith(PLAYLIST_EXTENSIONS) and not archives.is_generic_name(name)}
    if games <= {strip_tags(folder_name).lower()}:
        return True
    return len(games) == 1 and not folder_names and not SORT_FOLDER.fullmatch(folder_name)

def is_game_folder(folder_name, file_names, folder_names=()) -> bool:
    """
    Does the folder hold a single disc-based game, by the names of the files (and folders) right in it:
      - an extracted disc, with the files like "SYSTEM.CNF" or "PS3_DISC.SFB", or a "PS3_GAME" folder,
      - a disc sheet, like ".cue" for ".bin" or ".iso" tracks, or a file with a generic name, like "game.iso",
        when the other files are of one game (see _is_of_one_game).
    The second check keeps away the folders of many games, like the lettered ones of --sort.
    """
    if any(name.lower() in DISC_ROOT_FILES for name in file_names) \
            or any(name.lower() in DISC_ROOT_FOLDERS for name in folder_names):
        return True
    has_hint = any(name.lower().endswith(SHEET_EXTENSIONS) or archives.is_generic_name(name) for name in file_names)
    return has_hint and _is_of_one_game(folder_name, file_names, folder_names)

def find_game_folders(files_list) -> list[str]:
    """
    The folders of disc-based games (see is_game_folder) among the folders of the files, outer ones first.
    A game folder inside another one is a part of it, and the root folder is never a game folder.
    """
    files_in = {}
    folders_in = {}
    for path in files_list:
        folder, name = os.path.split(os.path.normpath(path))
        files_in.setdefault(folder, []).append(name)
        while folder:
            parent, child = os.path.split(folder)
            folders_in.setdefault(parent, set()).add(child)
            folder = parent

    game_folders = []
    for folder in sorted(set(files_in) | set(folders_in), key=lambda f: f.count(os.sep)):
        if not folder or any(folder.startswith(game + os.sep) for game in game_folders):
            continue
        if is_game_folder(os.path.basename(folder), files_in.get(folder, []), folders_in.get(folder, ())):
            game_folders.append(folder)
    return game_folders
