import sys
import os
import glob
import argparse
from dataclasses import dataclass
from enum import Flag, auto
import colorama
from colorama import Fore, Style
from multiprocessing import freeze_support

import archives
import duplicates
import operations
from tags import Release

version = "1.1.0"

class CategoryOption(Flag):
    HOMEBREW = auto()
    PIRATES = auto()
    SUBFOLDERS = auto()

def get_lettered_folder_name(filename) -> str:
    folder_name = filename[0].upper() if filename else ''
    if folder_name == "[":
        folder_name = "!!BIOS"
    elif not folder_name.isalpha():
        folder_name = "1-9"
    return folder_name

def try_add_subfolder(is_sort_subfolders, folder_name, filename) -> str:
    return (folder_name + "/" + get_lettered_folder_name(filename)) if is_sort_subfolders else folder_name

def get_new_folder(filename, separation_options, sorting_options, subfolders, excludes) -> str:
    release = Release.parse(filename)
    file_tags = release.tags
    excludes = {exclude.lower() for exclude in excludes} if excludes is not None else None
    
    # Check for 'homebrew' or 'aftermarket' tags
    if separation_options & CategoryOption.HOMEBREW and release.is_homebrew:
        folder_name = try_add_subfolder(sorting_options & CategoryOption.HOMEBREW, "!Homebrew", filename)
        
    # Check for 'pirate' or 'unl' tags
    elif separation_options & CategoryOption.PIRATES and release.is_pirate:
        folder_name = try_add_subfolder(sorting_options & CategoryOption.PIRATES, "!Pirates", filename)

    # Check for any user-defined 'subfolders' value matches any tag.
    elif subfolders is not None:
        found_subfolder = ""
        for subfolder in subfolders:
            if subfolder.lower() in file_tags and (excludes is None or not bool(excludes.intersection(file_tags))):
                found_subfolder = "!" + subfolder
                break
        folder_name = try_add_subfolder(sorting_options & CategoryOption.SUBFOLDERS, found_subfolder, filename) \
            if found_subfolder != "" else get_lettered_folder_name(filename)

    # Default to alphabetical folder
    else:
        folder_name = get_lettered_folder_name(filename)

    return folder_name

def remove_meta_files(path, is_log_enabled):
    for dirpath, dirnames, filenames in os.walk(path):
        for f in filenames:
            if f.lower() in ("desktop.ini", "thumbs.db", ".ds_store"):
                file_path = os.path.join(dirpath, f)
                os.remove(file_path)
                if is_log_enabled:
                    print(f"Removed meta file: {Fore.RED}{file_path}{Style.RESET_ALL}")

def remove_empty_subfolders(path, is_log_enabled):
    for dirpath, dirnames, filenames in os.walk(path, topdown=False):
        if not dirnames and not filenames:
            if dirpath != path:
                os.rmdir(dirpath)
                if is_log_enabled:
                    print(f"Removed empty folder: {Fore.RED}{dirpath}{Style.RESET_ALL}")
                # Kinda cludgy, but keep removing empty parent folders until we hit the root, to clear empty trees
                parent_dir = os.path.dirname(dirpath)
                while parent_dir != path and not os.listdir(parent_dir):
                    os.rmdir(parent_dir)
                    if is_log_enabled:
                        print(f"Removed empty folder: {Fore.RED}{parent_dir}{Style.RESET_ALL}")
                    parent_dir = os.path.dirname(parent_dir)

DUPLICATES_ACTIONS = {
    "ask": duplicates.Action.ASK,
    "all": duplicates.Action.KEEP_ALL,
    "one": duplicates.Action.KEEP_ONE,
}

@dataclass(frozen=True)
class Options:
    """Everything the command line can ask for."""
    input_folder: str
    is_sort_enabled: bool
    is_reverse_sort: bool
    sort_options: CategoryOption
    separation_options: CategoryOption
    subfolders: list
    exclude_tags: list
    is_unpacking_enabled: bool
    is_packing_enabled: bool
    packing_format: str
    is_remove_duplicates: bool
    remove_duplicates_action: duplicates.Action
    is_log_enabled: bool
    is_debug_log: bool
    is_dry_run: bool

def parse_category_flags(value, allowed) -> CategoryOption:
    """Reads option letters like 'hp', where 'a' stands for all the allowed ones."""
    flags = {"h": CategoryOption.HOMEBREW, "p": CategoryOption.PIRATES, "f": CategoryOption.SUBFOLDERS}
    result = CategoryOption(0)
    for letter in value:
        if letter == "a":
            for allowed_letter in allowed:
                result |= flags[allowed_letter]
        elif letter in allowed:
            result |= flags[letter]
        else:
            raise argparse.ArgumentTypeError(f"unknown option '{value}', use '{allowed}' letters, 'a' or 'none'")
    return result

def sort_argument(value):
    if value == "reverse":
        return value
    return CategoryOption(0) if value == "none" else parse_category_flags(value, "hpf")

def unlicensed_argument(value) -> CategoryOption:
    return CategoryOption(0) if value == "none" else parse_category_flags(value, "hp")

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="romlm", usage="%(prog)s [parameters]", add_help=False, allow_abbrev=False,
        formatter_class=lambda prog: argparse.RawTextHelpFormatter(prog, max_help_position=29),
        epilog="For more details and examples or to support an author,\n"
               "please check the README file or visit the GitHub repository:\n"
               f"{Fore.CYAN}https://github.com/ManeFunction/romlm{Style.RESET_ALL}")

    parser.add_argument("-i", "--input", metavar="folder", default=".",
        help="Specify the input folder.\nDefault is the current folder.\n")
    parser.add_argument("-s", "--sort", metavar="options", nargs="?", const=True, type=sort_argument,
        help="Sort files into lettered subfolders (A-Z).\n"
             "Options indicates is special folders should be\n"
             "also sorted. Can be:\n"
             "'h' - homebrew\n"
             "'p' - pirates\n"
             "'f' - user-defined folders\n"
             "'a' - all\n"
             "or use any combinations, like 'hp' or 'ps'.\n"
             "'reverse' - un-sort ROMs, placing all in the root.\n")
    archives = parser.add_mutually_exclusive_group()
    archives.add_argument("-x", "--extract", action="store_true",
        help="Extract all 7z/zip files in the folder.\n")
    archives.add_argument("-p", "--pack", metavar="format", nargs="?", const="7z", choices=("7z", "zip"),
        help="Pack all files in the folder to 7z/zip format.\n"
             "[format] can be '7z' or 'zip'. Default is '7z'.\n")
    parser.add_argument("-u", "--unlicensed", metavar="options", nargs="?", const=CategoryOption(0), type=unlicensed_argument,
        help="Disable Homebrew and Pirate stuff separation\n"
             "to the different folders. [options] can be:\n"
             "'h' - separate homebrew only\n"
             "'p' - separate pirates only\n"
             "'none' - do not separate anything\n"
             "Separation enabled by default.\n")
    parser.add_argument("-r", "--remove-duplicates", metavar="action", nargs="?", const=True, choices=tuple(DUPLICATES_ACTIONS),
        help="Remove duplicate files.\n"
             "When program stuck with more than one 'best' ROMs:\n"
             "'ask' - will ask which file to keep.\n"
             "'all' - will keep all best files.\n"
             "'one' - will keep only one best file (the first by name).\n"
             "If --log, default is 'ask', otherwise 'all'.\n"
             "--log is recommended for this process.\n")
    parser.add_argument("-f", "--folders", metavar="list", type=lambda value: value.split(","),
        help="Define subfolders to place files, based on tags.\n")
    parser.add_argument("-e", "--exclude", metavar="list", type=lambda value: value.split(","),
        help="Exclude files with specified tags from -f process.\n")
    parser.add_argument("-n", "--dry-run", action="store_true",
        help="Show what would be done, without changing anything.\nImplies --log.\n")
    parser.add_argument("-h", "--help", action="help", help="Show this help message.\n")
    parser.add_argument("-l", "--log", action="store_true", help="Enable full logging instead of progressbars.\n")
    parser.add_argument("-v", "--version", action="version", version=f"ROMs Library Manager v{version}",
        help="Show the version.")
    parser.add_argument("--debug", action="store_true", help=argparse.SUPPRESS)
    return parser

def parse_options(argv) -> Options:
    args = build_parser().parse_args(argv)

    # Defaults of the optional-value flags: -s without a value, or -r without an action
    sort = args.sort
    remove_duplicates_action = DUPLICATES_ACTIONS.get(args.remove_duplicates, duplicates.Action.NOT_DEFINED)
    if remove_duplicates_action == duplicates.Action.NOT_DEFINED:
        remove_duplicates_action = duplicates.Action.ASK if args.log else duplicates.Action.KEEP_ALL

    return Options(
        input_folder=args.input,
        is_sort_enabled=sort is not None,
        is_reverse_sort=isinstance(sort, str),
        sort_options=sort if isinstance(sort, CategoryOption) else CategoryOption(0),
        separation_options=CategoryOption.HOMEBREW | CategoryOption.PIRATES if args.unlicensed is None else args.unlicensed,
        subfolders=args.folders,
        exclude_tags=args.exclude,
        is_unpacking_enabled=args.extract,
        is_packing_enabled=args.pack is not None,
        packing_format=args.pack or "7z",
        is_remove_duplicates=args.remove_duplicates is not None,
        remove_duplicates_action=remove_duplicates_action,
        is_log_enabled=args.log or args.dry_run,
        is_debug_log=args.debug,
        is_dry_run=args.dry_run,
    )

def target_folder_for(file_name, options) -> str:
    if options.is_sort_enabled:
        if options.is_reverse_sort:
            return '.'
        return get_new_folder(os.path.basename(file_name), options.separation_options, options.sort_options,
                              options.subfolders, options.exclude_tags)
    return os.path.dirname(file_name)

def summarize_dry_run(duplicates_removed, planned) -> str:
    """A line about the amount of work a dry run found."""
    counts = [(duplicates_removed, "duplicate(s) to remove")]
    for kind, label in ((operations.Kind.MOVE, "to move"), (operations.Kind.PACK, "to pack"),
                        (operations.Kind.UNPACK, "to unpack")):
        counts.append((sum(1 for op in planned if op.kind == kind), f"file(s) {label}"))
    found = [f"{count} {label}" for count, label in counts if count > 0]
    return "Summary: " + ", ".join(found) + "." if found else "Summary: nothing to do."

def run(options):
    print(f">> Welcome to ROMs Library Manager (v{version})")
    if options.is_dry_run:
        print(f"{Fore.YELLOW}>> DRY RUN: nothing will be changed.{Style.RESET_ALL}")
    if options.is_log_enabled and options.subfolders is not None:
        print("Subfolders:", options.subfolders)
    if options.is_log_enabled and options.exclude_tags is not None:
        print("Exclude tags:", options.exclude_tags)

    if not (options.is_sort_enabled or options.is_unpacking_enabled or options.is_packing_enabled
            or options.is_remove_duplicates):
        print(f"{Fore.YELLOW}Nothing to do...{Style.RESET_ALL}")
        sys.exit()

    if (options.is_unpacking_enabled or (options.is_packing_enabled and options.packing_format == "7z")) \
            and archives.find_seven_zip_binary() is None:
        print(f"{Fore.RED}Error: No 7-Zip binary (7zz/7z/7za) found on PATH.{Style.RESET_ALL}")
        print("Install 7-Zip and make sure it's on your PATH, e.g. 'brew install sevenzip' on macOS/Linux.")
        sys.exit(1)

    if not os.path.exists(options.input_folder):
        print(f"{Fore.RED}Error: The specified input folder '{options.input_folder}' does not exist.{Style.RESET_ALL}")
        sys.exit(1)
    os.chdir(options.input_folder)
    print(f"Current working directory set to: {os.getcwd()}")

    if options.exclude_tags is not None and options.subfolders is None:
        print(f"{Fore.YELLOW}Warning: You cannot use --exclude without --subfolders. Option ignored.{Style.RESET_ALL}")

    # Get files list
    files_list = [f for f in glob.glob("**/*.*", recursive=True) if os.path.isfile(f)]

    # If duplicates removal is enabled, do it first
    duplicates_removed = 0
    if options.is_remove_duplicates:
        files_was = len(files_list)
        files_list = duplicates.clean_duplicates(files_list, options.remove_duplicates_action,
                                                 options.is_log_enabled, options.is_debug_log,
                                                 remove=(lambda path: None) if options.is_dry_run else os.remove)
        duplicates_removed = files_was - len(files_list)
        if files_was != len(files_list):
            print(f"Total ROMs left after duplicates removal: {Fore.GREEN}{len(files_list)}{Style.RESET_ALL} "
                  f"out of {Fore.RED}{files_was}{Style.RESET_ALL}")
        else:
            print("No duplicates found...")

    # Process files
    failures = []
    planned = []
    if options.is_sort_enabled or options.is_unpacking_enabled or options.is_packing_enabled:
        if options.is_unpacking_enabled or options.is_packing_enabled:
            print(">> Preparing processing...")
        planned = operations.plan_operations(files_list, lambda file_name: target_folder_for(file_name, options),
                                             options.is_unpacking_enabled, options.is_packing_enabled,
                                             options.packing_format)

        print(">> Processing files...")
        failures = operations.run_operations(planned, options.is_log_enabled, options.is_dry_run)

        if not options.is_dry_run:
            remove_meta_files(".", options.is_log_enabled)
            remove_empty_subfolders(".", options.is_log_enabled)

    if failures:
        print(f"{Fore.RED}>> {len(failures)} file(s) failed:{Style.RESET_ALL}")
        for f_name, error in failures:
            print(f" - {Fore.RED}{f_name}{Style.RESET_ALL}: {error}")
        sys.exit(1)

    if options.is_dry_run:
        print(f"{Fore.YELLOW}>> DRY RUN is over, nothing was changed.{Style.RESET_ALL}")
        print(summarize_dry_run(duplicates_removed, planned))
        sys.exit()

    print(">> DONE!")
    sys.exit()

def mane():
    colorama.init()
    run(parse_options(sys.argv[1:]))

if __name__ == "__main__":
    freeze_support()
    mane()
