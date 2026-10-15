import os
import re
from dataclasses import dataclass, field
from enum import Enum
from tqdm import tqdm
from colorama import Fore, Style

import tags

class Action(Enum):
    NOT_DEFINED = 0
    ASK = 1
    KEEP_ALL = 2
    KEEP_ONE = 3

top_region_priority = "world"
region_priority = ["usa", "europe"]
asian_regions = ["japan", "asia", "china", "korea"]

# What a Homebrew ROM without any version tag is scored as: the initial release, 1.0.0.0
IMPLICIT_HOMEBREW_VERSION_SCORE = 1000000000

# Version number tag, like "1.1", "v1.1" or "v2.0.1.3"
VERSION_NUMBER = r"v?\d+(?:\.\d+){0,3}"

# Is ROM a part of multi-disc set?
def get_disc_number(tags_list) -> int:
    """
    Returns '-1' if the ROM is not a part of a multi-disc set, or disc number otherwise.
    """
    for t in tags_list:
        m = re.match(r"(disc|disk|track)\s*(\d+)", t)
        if m:
            return int(m.group(2))
    return -1

# Helper: parse date like (1993-07-09)
def parse_date_yyyy_mm_dd(tag: str) -> bool:
    """
    Return True if tag looks like YYYY-MM-DD, else False.
    We won't parse the integer, we just treat "has date" as a boolean.
    """
    return bool(re.match(r"^\d{4}-\d{2}-\d{2}$", tag))

# Identify if file is Beta/Proto/Sample
def is_beta_file(fpath):
    tags_list = tags.get_from_filename(os.path.basename(fpath))
    for t in tags_list:
        # If it starts with "beta", "proto", or "sample", we treat it as Beta/Proto
        if (t.startswith("beta")
                or t.startswith("alpha")
                or t.startswith("proto")
                or t.startswith("sample")
                or t.startswith("demo")):
            return True
    return False

# Region coverage + min region index
def get_region_coverage_and_min_index(tags_list):
    """
    Returns (coverage, min_index) where:
      coverage = number of recognized region tags
      min_index = the lowest index among recognized tags (or len(region_priority) if none)
    Example: if tags_list has ["usa", "europe"], coverage=2, min_index=1 ("usa")
    """
    # Check if it's a top region priority
    for t in tags_list:
        if t == top_region_priority:
            return len(region_priority), 0
    # Check if it's a recognized prioritized region
    recognized = [r for r in tags_list if r in region_priority]
    coverage = len(recognized)
    if coverage == 0:
        return 0, len(region_priority)
    # find the lowest region index among them
    min_i = min(region_priority.index(r) for r in recognized)
    return coverage, min_i

# Is ROM from an Asian region?
def is_asian_region_and_not_en(tags_list):
    """
    Returns True if the ROM is from an Asian region and not in English.
    """
    is_asian = False
    is_en = False
    for t in tags_list:
        if t in asian_regions:
            is_asian = True
        elif t == "en":
            is_en = True
    return is_asian and not is_en

# Count how many unknown tags ROM have (excluding rev, beta/proto, sample, known region)
def count_unknown_tags(tags_list):
    count = 0
    for t in tags_list:
        # Skip known regions tags
        if t == top_region_priority:
            continue
        if t in region_priority:
            continue
        if t in asian_regions:
            continue
        # Revisions and versions tags
        if t.startswith("rev ") or re.match(rf"^{VERSION_NUMBER}$", t):
            continue
        # Beta and other in-development tags
        if t.startswith("beta") or t.startswith("alpha") or t.startswith("proto") or t.startswith("sample"):
            continue
        # Language tags
        if t in ["en", "fr", "de", "es", "it", "nl", "pt", "sv", "no", "da", "fi"]:
            continue
        # anything else is "extra"
        count += 1
    return count

# Get video format score for comparison (NTSC > none > PAL)
def get_video_format_score(tags_list) -> int:
    """
    Convert a video format tag into a single integer for comparison.
    """
    if "ntsc" in tags_list:
        return 2
    if "pal" in tags_list:
        return 0
    return 1

# Try to get version from tags list
def try_get_version_score(tags_list) -> tuple[int, bool]:
    for t in tags_list:
        # Catch numeric revisions
        m = re.match(r"^(rev|proto|alpha|beta|sample|demo)\s+([a-z])$", t)
        if m:
            rev = m.group(2)[0]
            rev_score = ord(rev) - ord('a') + 1
            return rev_score, True
        # Catch version numbers
        m = re.match(r"^(?:(rev|beta|alpha|proto|sample|demo)\s+)?v?(\d+(?:\.\d+){0,3})$", t)
        if m:
            version_str = m.group(2)
            parts = version_str.split(".")
            version_tuple = tuple(map(int, parts)) + (0,) * (4 - len(parts))
            version_score = int("".join(f"{v:03}" for v in version_tuple))
            return version_score, True
    return 0, False

# Get the date score from tags list
def get_date_score(tags_list) -> int:
    for t in tags_list:
        if parse_date_yyyy_mm_dd(t):
            date_score = int(t.replace("-", ""))
            return date_score
    return 0

# Normal-file scoring: ( non_region_tags, -region_coverage, min_region_index, -video_format, -revision, -date )
def score_normal_file(fpath, is_debug_log):
    tags_list = tags.get_from_filename(os.path.basename(fpath))

    coverage, min_idx = get_region_coverage_and_min_index(tags_list)
    video_format_score = get_video_format_score(tags_list)
    non_region = count_unknown_tags(tags_list)
    date_score = get_date_score(tags_list)

    version_score, version_found = try_get_version_score(tags_list)

    # Set a slight tags penalty for Asian regions to prioritize english versions even it's new (from Virtual Consoles, etc.)
    if is_asian_region_and_not_en(tags_list):
        non_region += 2

    # For Homebrew, assume that no explicit revision version is 1.0.0.0 (initial release)
    # ...for retro ROMs, it's more likely "Rev 0" (initial release)
    # also compensate missed initial revision for Homebrew 
    if (tags.is_homebrew(tags_list) or tags.is_pirate(tags_list)) and not version_found:
        version_score = IMPLICIT_HOMEBREW_VERSION_SCORE
        non_region += 1

    if is_debug_log:
        print(f"  >>> {fpath} (RELEASE): {Fore.MAGENTA}tags({non_region}), reg({coverage}: {min_idx}), "
              f"format({video_format_score}), v({version_score}:{date_score}){Style.RESET_ALL}")

    return (
        non_region,
        -coverage,
        min_idx,
        -video_format_score,
        -version_score,
        -date_score
    )

# Beta/Proto scoring: ( -latest_date, -region_coverage, -beta_number, non_region_tags )
def score_beta_file(fpath, is_debug_log):
    tags_list = tags.get_from_filename(os.path.basename(fpath))

    coverage, _ = get_region_coverage_and_min_index(tags_list)
    best_date_score = get_date_score(tags_list)
    non_region = count_unknown_tags(tags_list)

    version_score, _ = try_get_version_score(tags_list)

    if is_debug_log:
        print(f"  >>> {fpath} (BETA): {Fore.MAGENTA}date({best_date_score}), reg({coverage}), v({version_score}), "
              f"tags({non_region}){Style.RESET_ALL}")

    return (
        -best_date_score,
        -coverage,
        -version_score,
        non_region
    )

# Print list of files in a color
def print_files_list(files_list, color):
    for file_name in files_list:
        print(f" - {color}{os.path.basename(file_name)}{Style.RESET_ALL}")

@dataclass
class GroupPlan:
    """What to do with the files of one game. Made without touching the disk."""
    keep: list = field(default_factory=list)            # files that are kept for sure
    remove: list = field(default_factory=list)          # worse files that are deleted
    betas_dropped: list = field(default_factory=list)   # betas that are deleted because a release exists
    releases: list = field(default_factory=list)        # ...and those releases
    ties: list = field(default_factory=list)            # equally good files, the action decides which are kept
    is_beta_group: bool = False
    verdict: str = ""                                   # log label for the kept file, if it is only one

def plan_group(paths, is_debug_log) -> GroupPlan:
    """
    Decide which files of one game to keep:
      1) Partition into normal vs beta/proto.
         - If normal exists => all beta/proto are removed.
      2) Among normal => pick the best-scored normal file(s):
         - Fewer non-region tags
         - Region coverage (more is better)
         - Better (lower) region priority index
         - Better video format (NTSC > none > PAL)
         - Higher revision or version
         - Later date
         Several equally good files are returned as ties.
      3) If no normal => pick exactly one best-scored beta/proto (the first one on a tie):
         - Later date
         - Region coverage (more is better)
         - Higher revision or version
         - Fewer non-region tags
    Never plans to remove all the files of a game.
    """
    if len(paths) == 1:
        return GroupPlan(keep=list(paths), verdict="Single ROM")

    normal_files = []
    beta_files = []
    for p in paths:
        (beta_files if is_beta_file(p) else normal_files).append(p)

    if not normal_files:
        if len(beta_files) == 1:
            return GroupPlan(keep=beta_files, verdict="Single Beta")
        best = min(beta_files, key=lambda p: score_beta_file(p, is_debug_log))
        return GroupPlan(keep=[best], remove=[p for p in beta_files if p != best],
                         is_beta_group=True, verdict="Latest Beta")

    plan = GroupPlan(betas_dropped=beta_files, releases=normal_files)
    if len(normal_files) == 1:
        plan.keep = normal_files
        plan.verdict = "Single release ROM"
        return plan

    scores = {p: score_normal_file(p, is_debug_log) for p in normal_files}
    best_score = min(scores.values())
    best = [p for p in normal_files if scores[p] == best_score]
    plan.remove = [p for p in normal_files if scores[p] != best_score]
    plan.verdict = "Best ROM"
    if len(best) == 1:
        plan.keep = best
    else:
        plan.ties = best
    return plan

def ask_which_to_keep(candidates, number):
    """Asks the user which file to keep. Returns None if all of them should be kept."""
    print(f"{number}Can't decide which one is the best. Please select one to keep:")
    for idx, file in enumerate(candidates, start=1):
        print(f" {idx}. {Fore.YELLOW}{os.path.basename(file)}{Style.RESET_ALL}")

    selected_index = -1
    while selected_index < 0 or selected_index > len(candidates):
        try:
            selected_index = int(input("Enter the number of the file to keep (0 to keep all): "))
        except ValueError:
            print("Invalid input. Please enter a number.")

    return candidates[selected_index - 1] if selected_index > 0 else None

# Left only one file in the set
def keep_one(files_list, selected, is_log_enabled, number) -> list:
    if is_log_enabled:
        print(f"{number}Removing duplicate(s):")
    for file_name in files_list:
        if file_name != selected:
            if is_log_enabled:
                print(f"- {Fore.RED}{os.path.basename(file_name)}{Style.RESET_ALL}")
            os.remove(file_name)
    if is_log_enabled:
        print(f"| >> Keeping one: {Fore.GREEN}{os.path.basename(selected)}{Style.RESET_ALL}")
    return [selected]

def resolve_ties(ties, action, is_log_enabled, number) -> list:
    """Removes the files that the action doesn't keep, and returns the kept ones."""
    if action == Action.KEEP_ONE:
        return keep_one(ties, min(ties), is_log_enabled, number)

    if action == Action.ASK:
        selected = ask_which_to_keep(ties, number)
        if selected is not None:
            return keep_one(ties, selected, is_log_enabled, number)

    if is_log_enabled:
        print(f"{number}Keeping all best ROMs:")
        print_files_list(ties, Fore.GREEN)
    return ties

def apply_group(plan, action, is_log_enabled, number) -> list:
    """Carries out the plan: removes files, asks and logs. Returns the files that are kept."""
    if not plan.keep and not plan.ties:
        raise ValueError("Refusing to remove all the files of a game")

    if plan.betas_dropped:
        if is_log_enabled:
            print(f"{number}Removing all Betas: ")
            print_files_list(plan.betas_dropped, Fore.RED)
            print(f" | >> Has {len(plan.releases)} release(s):")
            print_files_list(plan.releases, Fore.GREEN)
        for f in plan.betas_dropped:
            os.remove(f)

    label = "Removing earlier Beta" if plan.is_beta_group else "Removing duplicate"
    for f in plan.remove:
        if is_log_enabled:
            print(f"{number}{label}: {Fore.RED}{os.path.basename(f)}{Style.RESET_ALL}")
        os.remove(f)

    kept = list(plan.keep)
    if plan.ties:
        kept += resolve_ties(plan.ties, action, is_log_enabled, number)

    if is_log_enabled and len(kept) == 1:
        print(f"{number}{plan.verdict}: {Fore.GREEN}{os.path.basename(kept[0])}{Style.RESET_ALL}")
    return kept

def clean_duplicates(file_list, action, is_log_enabled, is_debug_log):
    """
    Removes the worse files of every game (see plan_group), and returns the files that are left.
    [BIOS] files are never grouped nor removed.
    """

    # Group files by base name
    file_list = list(file_list)
    by_basename = {}

    # BIOS files are named "[BIOS] System (Region)", so they have no game name to group by
    bios_files = {f for f in file_list if tags.is_bios(f)}

    for f in file_list:
        if f in bios_files:
            continue
        fname = os.path.basename(f)
        base = tags.get_base_name(fname)
        disc = get_disc_number(tags.get_from_filename(fname))
        if disc > -1:
            base += f" (Disc {disc})"
        by_basename.setdefault(base, []).append(f)

    print(
        ">> Removing duplicates safely... \nTotal ROMs:",
        len(file_list),
        "\nActual games:",
        len(by_basename),
    )

    files_to_keep = set(bios_files)

    # MAIN LOOP of removing duplicates
    groups_iter = by_basename.items() if is_log_enabled \
        else tqdm(by_basename.items(), desc="Cleaning Duplicates", total=len(by_basename))

    for i, (base, paths) in enumerate(groups_iter, start=1):
        plan = plan_group(paths, is_debug_log)
        files_to_keep.update(apply_group(plan, action, is_log_enabled, f"({i}/{len(by_basename)}) "))

    # Return only files we decided to keep
    return [f for f in file_list if f in files_to_keep]
