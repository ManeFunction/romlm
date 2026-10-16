import os
import re
from dataclasses import dataclass

# Regions, from the most to the least preferred (see duplicates scoring)
TOP_REGION = "world"
REGION_PRIORITY = ["usa", "europe"]
ASIAN_REGIONS = ["japan", "asia", "china", "korea"]

LANGUAGES = ["en", "fr", "de", "es", "it", "nl", "pt", "sv", "no", "da", "fi"]

# Tags of the not finished releases are starting with these
DEV_PREFIXES = ("beta", "alpha", "proto", "sample", "demo")

# Version number tag, like "1.1", "v1.1" or "v2.0.1.3"
VERSION_NUMBER = r"v?\d+(?:\.\d+){0,3}"

def get_from_filename(filename: str) -> list[str]:
    name_no_ext = os.path.splitext(filename)[0]
    groups = re.findall(r'[(\[](.*?)[)\]]', name_no_ext)
    all_tags = []
    for g in groups:
        split_tags = [t.strip() for t in g.split(',')]
        all_tags.extend(split_tags)
    return [tag.lower() for tag in all_tags]

def get_base_name(filename: str) -> str:
    name_no_ext = os.path.splitext(filename)[0]
    idx_1 = name_no_ext.find('(')
    idx_2 = name_no_ext.find('[')
    idx = min(idx_1, idx_2) if idx_1 != -1 and idx_2 != -1 else max(idx_1, idx_2)
    if idx != -1:
        base = name_no_ext[:idx].strip()
    else:
        base = name_no_ext.strip()
    return base

# Disc tag, like "disc 2" or "track 03"
DISC_PATTERN = re.compile(r"(disc|disk|track)\s*(\d+)")

def get_disc_number(tags_list) -> int:
    """
    Returns '-1' if the ROM is not a part of a multi-disc set, or disc number otherwise.
    """
    for t in tags_list:
        m = DISC_PATTERN.match(t)
        if m:
            return int(m.group(2))
    return -1

@dataclass(frozen=True)
class Release:
    """Everything the file name tells about a ROM. Parse it once with Release.parse()."""
    path: str
    name: str                 # file name with the extension
    base_name: str            # the game name, without tags
    tags: tuple               # lowercase, from all of the (...) and [...] groups
    disc: int                 # -1 if it is not a part of a multi-disc set
    is_bios: bool
    is_homebrew: bool
    is_pirate: bool
    is_beta: bool             # beta, proto, sample and other not finished releases

    @classmethod
    def parse(cls, path: str) -> "Release":
        name = os.path.basename(path)
        file_tags = tuple(get_from_filename(name))
        return cls(
            path=path,
            name=name,
            base_name=get_base_name(name),
            tags=file_tags,
            disc=get_disc_number(file_tags),
            is_bios=name.lower().startswith("[bios]"),
            is_homebrew="homebrew" in file_tags or "aftermarket" in file_tags,
            is_pirate="pirate" in file_tags or "unl" in file_tags,
            is_beta=any(t.startswith(DEV_PREFIXES) for t in file_tags),
        )

    @property
    def game_key(self) -> str:
        """The same for all the files of one game (each disc is a game of its own)."""
        return f"{self.base_name} (Disc {self.disc})" if self.disc > -1 else self.base_name
