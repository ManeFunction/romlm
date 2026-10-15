import os
import re
from dataclasses import dataclass, field
from enum import Enum
from tqdm import tqdm
from colorama import Fore, Style

import tags
from tags import Release

class Action(Enum):
    NOT_DEFINED = 0
    ASK = 1
    KEEP_ALL = 2
    KEEP_ONE = 3

# What a Homebrew ROM without any version tag is scored as: the initial release, 1.0.0.0
IMPLICIT_HOMEBREW_VERSION_SCORE = 1000000000

# Helper: is the tag a date like (1993-07-09)
def is_date_tag(tag: str) -> bool:
    """
    Return True if tag looks like YYYY-MM-DD, else False.
    We won't parse the integer, we just treat "has date" as a boolean.
    """
    return bool(re.match(r"^\d{4}-\d{2}-\d{2}$", tag))

# Region coverage + min region index
def get_region_coverage_and_min_index(tags_list):
    """
    Returns (coverage, min_index) where:
      coverage = number of recognized region tags
      min_index = the lowest index among recognized tags (or len(REGION_PRIORITY) if none)
    Example: if tags_list has ["usa", "europe"], coverage=2, min_index=1 ("usa")
    """
    # Check if it's a top region priority
    for t in tags_list:
        if t == tags.TOP_REGION:
            return len(tags.REGION_PRIORITY), 0
    # Check if it's a recognized prioritized region
    recognized = [r for r in tags_list if r in tags.REGION_PRIORITY]
    coverage = len(recognized)
    if coverage == 0:
        return 0, len(tags.REGION_PRIORITY)
    # find the lowest region index among them
    min_i = min(tags.REGION_PRIORITY.index(r) for r in recognized)
    return coverage, min_i

# Is ROM from an Asian region?
def is_asian_region_and_not_en(tags_list):
    """
    Returns True if the ROM is from an Asian region and not in English.
    """
    is_asian = False
    is_en = False
    for t in tags_list:
        if t in tags.ASIAN_REGIONS:
            is_asian = True
        elif t == "en":
            is_en = True
    return is_asian and not is_en

# Count how many unknown tags ROM have (excluding rev, beta/proto, sample, known region)
def count_unknown_tags(tags_list):
    count = 0
    for t in tags_list:
        # Skip known regions tags
        if t == tags.TOP_REGION or t in tags.REGION_PRIORITY or t in tags.ASIAN_REGIONS:
            continue
        # Revisions and versions tags
        if t.startswith("rev ") or re.match(rf"^{tags.VERSION_NUMBER}$", t):
            continue
        # Beta and other in-development tags
        if t.startswith(tags.DEV_PREFIXES):
            continue
        # Language tags
        if t in tags.LANGUAGES:
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
        if is_date_tag(t):
            date_score = int(t.replace("-", ""))
            return date_score
    return 0

# Normal-file scoring: ( non_region_tags, -region_coverage, min_region_index, -video_format, -revision, -date )
def score_normal_file(release, is_debug_log):
    tags_list = release.tags

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
    if (release.is_homebrew or release.is_pirate) and not version_found:
        version_score = IMPLICIT_HOMEBREW_VERSION_SCORE
        non_region += 1

    if is_debug_log:
        print(f"  >>> {release.path} (RELEASE): {Fore.MAGENTA}tags({non_region}), reg({coverage}: {min_idx}), "
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
def score_beta_file(release, is_debug_log):
    tags_list = release.tags

    coverage, _ = get_region_coverage_and_min_index(tags_list)
    best_date_score = get_date_score(tags_list)
    non_region = count_unknown_tags(tags_list)

    version_score, _ = try_get_version_score(tags_list)

    if is_debug_log:
        print(f"  >>> {release.path} (BETA): {Fore.MAGENTA}date({best_date_score}), reg({coverage}), v({version_score}), "
              f"tags({non_region}){Style.RESET_ALL}")

    return (
        -best_date_score,
        -coverage,
        -version_score,
        non_region
    )

# Print list of releases in a color
def print_files_list(releases, color):
    for release in releases:
        print(f" - {color}{release.name}{Style.RESET_ALL}")

@dataclass
class GroupPlan:
    """What to do with the files of one game. Made without touching the disk."""
    keep: list = field(default_factory=list)            # releases that are kept for sure
    remove: list = field(default_factory=list)          # worse releases that are deleted
    betas_dropped: list = field(default_factory=list)   # betas that are deleted because a release exists
    releases: list = field(default_factory=list)        # ...and those releases
    ties: list = field(default_factory=list)            # equally good releases, the action decides which are kept
    is_beta_group: bool = False
    verdict: str = ""                                   # log label for the kept file, if it is only one

def plan_group(releases, is_debug_log) -> GroupPlan:
    """
    Decide which releases of one game to keep:
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
    if len(releases) == 1:
        return GroupPlan(keep=list(releases), verdict="Single ROM")

    normal_files = [r for r in releases if not r.is_beta]
    beta_files = [r for r in releases if r.is_beta]

    if not normal_files:
        if len(beta_files) == 1:
            return GroupPlan(keep=beta_files, verdict="Single Beta")
        best = min(beta_files, key=lambda r: score_beta_file(r, is_debug_log))
        return GroupPlan(keep=[best], remove=[r for r in beta_files if r is not best],
                         is_beta_group=True, verdict="Latest Beta")

    plan = GroupPlan(betas_dropped=beta_files, releases=normal_files)
    if len(normal_files) == 1:
        plan.keep = normal_files
        plan.verdict = "Single release ROM"
        return plan

    scores = [score_normal_file(r, is_debug_log) for r in normal_files]
    best_score = min(scores)
    best = [r for r, sc in zip(normal_files, scores) if sc == best_score]
    plan.remove = [r for r, sc in zip(normal_files, scores) if sc != best_score]
    plan.verdict = "Best ROM"
    if len(best) == 1:
        plan.keep = best
    else:
        plan.ties = best
    return plan

def ask_which_to_keep(candidates, number):
    """Asks the user which release to keep. Returns None if all of them should be kept."""
    print(f"{number}Can't decide which one is the best. Please select one to keep:")
    for idx, release in enumerate(candidates, start=1):
        print(f" {idx}. {Fore.YELLOW}{release.name}{Style.RESET_ALL}")

    selected_index = -1
    while selected_index < 0 or selected_index > len(candidates):
        try:
            selected_index = int(input("Enter the number of the file to keep (0 to keep all): "))
        except ValueError:
            print("Invalid input. Please enter a number.")

    return candidates[selected_index - 1] if selected_index > 0 else None

# Left only one release in the set
def keep_one(releases, selected, is_log_enabled, number) -> list:
    if is_log_enabled:
        print(f"{number}Removing duplicate(s):")
        for release in releases:
            if release is not selected:
                print(f"- {Fore.RED}{release.name}{Style.RESET_ALL}")
        print(f"| >> Keeping one: {Fore.GREEN}{selected.name}{Style.RESET_ALL}")
    return [selected]

def resolve_ties(ties, action, choose, is_log_enabled, number) -> list:
    """Picks the releases that the action keeps among the equally good ones."""
    if action == Action.KEEP_ONE:
        return keep_one(ties, min(ties, key=lambda r: r.path), is_log_enabled, number)

    if action == Action.ASK:
        selected = choose(ties, number)
        if selected is not None:
            return keep_one(ties, selected, is_log_enabled, number)

    if is_log_enabled:
        print(f"{number}Keeping all best ROMs:")
        print_files_list(ties, Fore.GREEN)
    return ties

@dataclass
class Decision:
    """The final verdict for one game. Nothing is removed until all the games are decided."""
    kept: list
    removed: list

def decide_group(plan, action, choose, is_log_enabled, number) -> Decision:
    """Settles the ties of the plan (asking if needed) and logs. Doesn't touch the files."""
    if not plan.keep and not plan.ties:
        raise ValueError("Refusing to remove all the files of a game")

    removed = list(plan.betas_dropped)
    if plan.betas_dropped and is_log_enabled:
        print(f"{number}Removing all Betas: ")
        print_files_list(plan.betas_dropped, Fore.RED)
        print(f" | >> Has {len(plan.releases)} release(s):")
        print_files_list(plan.releases, Fore.GREEN)

    label = "Removing earlier Beta" if plan.is_beta_group else "Removing duplicate"
    for r in plan.remove:
        if is_log_enabled:
            print(f"{number}{label}: {Fore.RED}{r.name}{Style.RESET_ALL}")
        removed.append(r)

    kept = list(plan.keep)
    if plan.ties:
        tied_kept = resolve_ties(plan.ties, action, choose, is_log_enabled, number)
        kept += tied_kept
        removed += [r for r in plan.ties if r not in tied_kept]

    if is_log_enabled and len(kept) == 1:
        print(f"{number}{plan.verdict}: {Fore.GREEN}{kept[0].name}{Style.RESET_ALL}")
    return Decision(kept, removed)

def clean_duplicates(file_list, action, is_log_enabled, is_debug_log, choose=ask_which_to_keep, remove=os.remove):
    """
    Removes the worse files of every game (see plan_group), and returns the files that are left.
    Everything is decided, including the questions to the user, before the first file is removed.
    [BIOS] files are never grouped nor removed.
    `choose` answers the questions of the Action.ASK, `remove` deletes a file.
    """

    # Group files by game
    file_list = list(file_list)
    by_game = {}

    # BIOS files are named "[BIOS] System (Region)", so they have no game name to group by
    files_to_keep = set()

    for f in file_list:
        release = Release.parse(f)
        if release.is_bios:
            files_to_keep.add(f)
        else:
            by_game.setdefault(release.game_key, []).append(release)

    print(
        ">> Removing duplicates safely... \nTotal ROMs:",
        len(file_list),
        "\nActual games:",
        len(by_game),
    )

    # MAIN LOOP of deciding what to remove
    groups_iter = by_game.values() if is_log_enabled \
        else tqdm(by_game.values(), desc="Cleaning Duplicates", total=len(by_game))

    files_to_remove = []
    for i, releases in enumerate(groups_iter, start=1):
        plan = plan_group(releases, is_debug_log)
        decision = decide_group(plan, action, choose, is_log_enabled, f"({i}/{len(by_game)}) ")
        files_to_keep.update(r.path for r in decision.kept)
        files_to_remove += [r.path for r in decision.removed]

    for path in files_to_remove:
        remove(path)

    # Return only files we decided to keep
    return [f for f in file_list if f in files_to_keep]
