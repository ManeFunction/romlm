import os
import re
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

# Is ROM a part of multi-disc set?
def get_disc_number(tags_list) -> int:
    """
    Returns '-1' if the ROM is not a part of a multi-disc set, or disc number otherwise.
    """
    for t in tags_list:
        m = re.match(r"(disc|disk)\s*(\d+)", t)
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
        if t.startswith("rev ") or re.match(r"^\d+(?:\.\d+){0,3}$", t):
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
        m = re.match(r"^(?:(rev|beta|alpha|proto|sample|demo)\s+)?v?(\d+(?:\.\d+){0,3})?$", t)
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

# Normal-file scoring: ( -region_coverage, min_region_index, non_region_tags, -video_format, -revision, -date )
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
        version_score = 100000000000
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

# Left only one file in the set
def keep_one(files_set, selected, is_log_enabled, number) -> set:
    if is_log_enabled:
        print(f"{number}Removing duplicate(s):")
    for file_name in files_set:
        if file_name != selected:
            if is_log_enabled:
                print(f"- {Fore.RED}{os.path.basename(file_name)}{Style.RESET_ALL}")
            os.remove(file_name)
    if is_log_enabled:
        print(f"| >> Keeping one: {Fore.GREEN}{os.path.basename(selected)}{Style.RESET_ALL}")
    return {selected}

def clean_duplicates(file_list, action, is_log_enabled, is_debug_log):
    """
    For each distinct base name (game):
      1) Partition into normal vs beta/proto.
         - If normal exists => remove all beta/proto.
      2) Among normal => pick exactly one best-scored normal file:
         - Region coverage (more is better)
         - Fewer non-region tags
         - Better (lower) region priority index
         - Higher revision
      3) If no normal => pick exactly one best-scored beta/proto:
         - Region coverage (more is better)
         - No date is better than having a date
         - Higher numeric suffix is better
         - Fewer non-region tags
      4) Remove the rest. Never remove all for a given game; if end up with none, keep them all.
    """

    # Get a log iteration string formatted as "(N/M)"
    def n(index) -> str:
        return f"({index}/{len(groups_iter)}) "

    # Group files by base name
    file_list = list(file_list)
    by_basename = {}

    for f in file_list:
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

    files_to_keep = set()

    # MAIN LOOP of removing duplicates
    groups_iter = by_basename.items() if is_log_enabled \
        else tqdm(by_basename.items(), desc="Cleaning Duplicates", total=len(by_basename))

    i = 0
    for base, paths in groups_iter:
        i += 1

        # Only one file => trivially keep it
        if len(paths) == 1:
            files_to_keep.add(paths[0])
            if is_log_enabled:
                print(f"{n(i)}Single ROM: {Fore.GREEN}{os.path.basename(paths[0])}{Style.RESET_ALL}")
            continue

        # Partition into normal vs. beta/proto
        normal_files = []
        beta_proto_files = []
        for p in paths:
            if is_beta_file(p):
                beta_proto_files.append(p)
            else:
                normal_files.append(p)

        if normal_files:
            # Remove all Beta/Proto
            chosen_set = normal_files
            if is_log_enabled and beta_proto_files:
                print(f"{n(i)}Removing all Betas: ")
                print_files_list(beta_proto_files, Fore.RED)
                print(f" | >> Has {len(normal_files)} release(s):")
                print_files_list(normal_files, Fore.GREEN)
            for bp in beta_proto_files:
                os.remove(bp)
        else:
            # No normal => only Beta/Proto
            # Pick exactly one best-scored
            if len(beta_proto_files) == 1:
                files_to_keep.add(beta_proto_files[0])
                if is_log_enabled:
                    print(f"{n(i)}Single Beta: {Fore.GREEN}{os.path.basename(beta_proto_files[0])}{Style.RESET_ALL}")
                continue

            best_bp = None
            best_score = None
            for bp in beta_proto_files:
                sc = score_beta_file(bp, is_debug_log)
                if (best_score is None) or (sc < best_score):
                    best_score = sc
                    best_bp = bp

            keep_set = {best_bp}
            for bp in beta_proto_files:
                if bp != best_bp:
                    if is_log_enabled:
                        print(f"{n(i)}Removing earlier Beta: {Fore.RED}{os.path.basename(bp)}{Style.RESET_ALL}")
                    os.remove(bp)

            # safety check: never remove all
            if not keep_set:
                # fallback => keep them all
                for p in beta_proto_files:
                    files_to_keep.add(p)
                if is_log_enabled:
                    print(f"{n(i)}No latest Beta, keeping all:")
                    print_files_list(beta_proto_files, Fore.GREEN)
            else:
                for f in keep_set:
                    files_to_keep.add(f)
                if is_log_enabled:
                    print(f"{n(i)}Latest Beta: {Fore.GREEN}{os.path.basename(best_bp)}{Style.RESET_ALL}")
            continue

        # If chosen_set is empty for some reason, fallback => keep them all
        if not chosen_set:
            for p in paths:
                files_to_keep.add(p)
            if is_log_enabled:
                print(f"{n(i)}No release ROMs, keeping all these:")
                print_files_list(paths, Fore.GREEN)
            continue

        # Among the chosen normal set, pick best scored files
        if len(chosen_set) == 1:
            files_to_keep.add(chosen_set[0])
            if is_log_enabled:
                print(f"{n(i)}Single release ROM: {Fore.GREEN}{os.path.basename(chosen_set[0])}{Style.RESET_ALL}")
            continue

        best_normal = set()
        best_score = None
        for nf in chosen_set:
            sc = score_normal_file(nf, is_debug_log)
            if (best_score is None) or (sc < best_score):
                best_score = sc
                best_normal = {nf}
            elif sc == best_score:
                best_normal.add(nf)

        # remove all others
        keep_set = best_normal
        for nf in chosen_set:
            if nf not in best_normal:
                if is_log_enabled:
                    print(f"{n(i)}Removing duplicate: {Fore.RED}{os.path.basename(nf)}{Style.RESET_ALL}")
                os.remove(nf)

        # safety check
        if not keep_set:
            # fallback => keep them all
            for f in chosen_set:
                files_to_keep.add(f)
            if is_log_enabled:
                print(f"{n(i)}No best ROM, keeping all:")
                print_files_list(chosen_set, Fore.GREEN)
        else:
            # check what we need to do with the rest of the best
            if len(keep_set) > 1:
                if action == Action.KEEP_ALL:
                    if is_log_enabled:
                        print(f"{n(i)}Keeping all best ROMs:")
                        print_files_list(keep_set, Fore.GREEN)

                elif action == Action.KEEP_ONE:
                    best_kept = min(keep_set, key=lambda x: x)
                    keep_set = keep_one(keep_set, best_kept, is_log_enabled, n(i))

                elif action == Action.ASK:
                    print(f"{n(i)}Can't decide which one is the best. Please select one to keep:")
                    keep_list = list(keep_set)
                    for idx, file in enumerate(keep_list, start=1):
                        print(f" {idx}. {Fore.YELLOW}{os.path.basename(file)}{Style.RESET_ALL}")

                    selected_index = -1
                    while selected_index < 0 or selected_index > len(keep_list):
                        try:
                            selected_index = int(input("Enter the number of the file to keep (0 to keep all): "))
                        except ValueError:
                            print("Invalid input. Please enter a number.")

                    if selected_index == 0:
                        if is_log_enabled:
                            print(f"{n(i)}Keeping all best ROMs:")
                            print_files_list(keep_set, Fore.GREEN)
                    else:
                        user_selected = keep_list[selected_index - 1]
                        keep_set = keep_one(keep_set, user_selected, is_log_enabled, n(i))

            if len(keep_set) == 1:
                if is_log_enabled:
                    print(f"{n(i)}Best ROM: {Fore.GREEN}{os.path.basename(next(iter(keep_set)))}{Style.RESET_ALL}")

            for f in keep_set:
                files_to_keep.add(f)

    # Return only files we decided to keep
    return [f for f in file_list if f in files_to_keep]