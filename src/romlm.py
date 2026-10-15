import sys
import os
import shutil
import glob
import subprocess
import argparse
from dataclasses import dataclass
from enum import Flag, auto
import zipfile
import colorama
from colorama import Fore, Style
from tqdm import tqdm
from multiprocessing import Pool, freeze_support

import tags
import duplicates

version = "1.1.0"

# Candidate binary names for a 7-Zip CLI, in preference order: "7zz" is what
# Homebrew's sevenzip formula installs; "7z"/"7za" are the common names from
# p7zip, apt/dnf packages, and the official Windows installer.
SEVEN_ZIP_BINARY_NAMES = ("7zz", "7z", "7za")


def find_seven_zip_binary():
	"""Locate a usable 7-Zip CLI binary on PATH, or None if none is installed."""
	for name in SEVEN_ZIP_BINARY_NAMES:
		path = shutil.which(name)
		if path:
			return path
	return None

class CategoryOption(Flag):
	HOMEBREW = auto()
	PIRATES = auto()
	SUBFOLDERS = auto()

def create_if_not_exist(folder):
	if not os.path.exists(folder):
		os.makedirs(folder)
		
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
	file_tags = tags.get_from_filename(filename)
	excludes = {exclude.lower() for exclude in excludes} if excludes is not None else None
	
	# Check for 'homebrew' or 'aftermarket' tags
	if separation_options & CategoryOption.HOMEBREW and tags.is_homebrew(file_tags):
		folder_name = try_add_subfolder(sorting_options & CategoryOption.HOMEBREW, "!Homebrew", filename)
		
	# Check for 'pirate' or 'unl' tags
	elif separation_options & CategoryOption.PIRATES and tags.is_pirate(file_tags):
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

	create_if_not_exist(folder_name)
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

def move_file(file_name, target_folder):
	"""Moves a file into the target folder. Returns a log line, or None if it is already there."""
	if os.path.normpath(os.path.dirname(file_name) or ".") == os.path.normpath(target_folder):
		return None
	shutil.move(file_name, os.path.join(target_folder, os.path.basename(file_name)))
	return f" >> Moved to: {Fore.BLUE}{target_folder}{Style.RESET_ALL}"

def describe_error(error) -> str:
	"""A one-line reason of why a file could not be processed."""
	if isinstance(error, subprocess.CalledProcessError):
		output = error.stderr or error.stdout or b""
		details = output.decode(errors="replace").strip().splitlines()
		return f"7-Zip failed with code {error.returncode}" + (f": {details[-1]}" if details else "")
	return f"{type(error).__name__}: {error}"

def process_file(args) -> tuple[str, str, str]:
	"""Processes a single file for packing or unpacking. Returns the file name, a log line and an error message."""
	file_name, target_folder, is_unpacking_enabled, is_packing_enabled, packing_format = args
	try:
		if is_unpacking_enabled and file_name.endswith((".7z", ".zip")):
			result_log = unpack_file(file_name, target_folder)
		elif is_packing_enabled and not file_name.endswith((".7z", ".zip")) and not tags.is_bios(file_name):
			result_log = pack_file(file_name, target_folder, packing_format)
		else:
			# Nothing to pack or unpack, but the file still has to follow the sorting
			result_log = move_file(file_name, target_folder)
	except Exception as error:
		return file_name, None, describe_error(error)
	return file_name, result_log, None

def unpack_file(file_name, target_folder) -> str:
	"""Handles unpacking of a single file."""
	if file_name.endswith(".7z"):
		seven_zip_bin = find_seven_zip_binary()
		subprocess.run(
			[seven_zip_bin, "x", os.path.abspath(file_name), f"-o{os.path.abspath(target_folder)}", "-y"],
			check=True, capture_output=True,
		)
	elif file_name.endswith(".zip"):
		with zipfile.ZipFile(file_name, 'r') as archive:
			archive.extractall(target_folder)
	os.remove(file_name)
	return f" >> Unpacked to: {Fore.BLUE}{target_folder}{Style.RESET_ALL}"

def pack_file(file_name, target_folder, packing_format) -> str:
	"""Handles packing of a single file."""
	archive_path = os.path.join(target_folder, os.path.basename(file_name))
	archive_file = f"{archive_path}.{packing_format}"
	try:
		if packing_format == "7z":
			seven_zip_bin = find_seven_zip_binary()
			# Run with cwd set to the source file's folder, passing only its basename,
			# so the archive stores just that name (matching the old arcname behavior)
			# instead of the full source path.
			subprocess.run(
				[seven_zip_bin, "a", os.path.abspath(archive_file), os.path.basename(file_name)],
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
	return f" >> Packed to: {Fore.BLUE}{archive_file}{Style.RESET_ALL}"

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
		is_log_enabled=args.log,
		is_debug_log=args.debug,
	)

def target_folder_for(file_name, options) -> str:
	if options.is_sort_enabled:
		if options.is_reverse_sort:
			return '.'
		return get_new_folder(os.path.basename(file_name), options.separation_options, options.sort_options,
							  options.subfolders, options.exclude_tags)
	return os.path.dirname(file_name)

def run(options):
	print(f">> Welcome to ROMs Library Manager (v{version})")
	if options.is_log_enabled and options.subfolders is not None:
		print("Subfolders:", options.subfolders)
	if options.is_log_enabled and options.exclude_tags is not None:
		print("Exclude tags:", options.exclude_tags)

	if not (options.is_sort_enabled or options.is_unpacking_enabled or options.is_packing_enabled
			or options.is_remove_duplicates):
		print(f"{Fore.YELLOW}Nothing to do...{Style.RESET_ALL}")
		sys.exit()

	if (options.is_unpacking_enabled or (options.is_packing_enabled and options.packing_format == "7z")) \
			and find_seven_zip_binary() is None:
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
	if options.is_remove_duplicates:
		files_was = len(files_list)
		files_list = duplicates.clean_duplicates(files_list, options.remove_duplicates_action,
												 options.is_log_enabled, options.is_debug_log)
		if files_was != len(files_list):
			print(f"Total ROMs left after duplicates removal: {Fore.GREEN}{len(files_list)}{Style.RESET_ALL} "
				  f"out of {Fore.RED}{files_was}{Style.RESET_ALL}")
		else:
			print("No duplicates found...")

	# Process files
	failures = []
	if options.is_sort_enabled or options.is_unpacking_enabled or options.is_packing_enabled:
		# Single-threaded processing for just a move operation
		if not options.is_unpacking_enabled and not options.is_packing_enabled:
			print(">> Processing files...")
			progress = files_list if options.is_log_enabled else tqdm(files_list, desc="Processing")

			for file_name in progress:
				result_log = move_file(file_name, target_folder_for(file_name, options))
				if options.is_log_enabled and result_log is not None:
					print(result_log)
		else:
			# Multithreaded processing for packing/unpacking
			print(">> Preparing processing...")
			tasks = [(file_name, target_folder_for(file_name, options), options.is_unpacking_enabled,
					  options.is_packing_enabled, options.packing_format) for file_name in files_list]

			print(">> Processing files...")
			if options.is_log_enabled:
				with Pool(processes=os.cpu_count()) as pool:
					for i, (f_name, result_log, error) in enumerate(pool.imap_unordered(process_file, tasks), start=1):
						if error is not None:
							failures.append((f_name, error))
							print(f"({i}/{len(tasks)}) Failed: {Fore.RED}{f_name}{Style.RESET_ALL} ({error})")
						else:
							print(f"({i}/{len(tasks)}) Processed: {Fore.GREEN}{f_name}{Style.RESET_ALL}")
							if result_log is not None:
								print(result_log)
			else:
				with Pool(processes=os.cpu_count()) as pool:
					with tqdm(total=len(tasks), desc="Processing") as progress:
						for f_name, _, error in pool.imap_unordered(process_file, tasks):
							if error is not None:
								failures.append((f_name, error))
							progress.update(1)

		remove_meta_files(".", options.is_log_enabled)
		remove_empty_subfolders(".", options.is_log_enabled)

	if failures:
		print(f"{Fore.RED}>> {len(failures)} file(s) failed:{Style.RESET_ALL}")
		for f_name, error in failures:
			print(f" - {Fore.RED}{f_name}{Style.RESET_ALL}: {error}")
		sys.exit(1)

	print(">> DONE!")
	sys.exit()

def mane():
	colorama.init()
	run(parse_options(sys.argv[1:]))

if __name__ == "__main__":
	freeze_support()
	mane()
