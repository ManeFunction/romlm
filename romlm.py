import sys
import os
import shutil
import glob
from enum import Flag, auto
import py7zr
import zipfile
import colorama
from colorama import Fore, Style
from tqdm import tqdm
from multiprocessing import Pool, freeze_support

import tags
import duplicates

version = "1.0.2"

def print_help():
	print("Usage: \033[1mromlm\033[0m [parameters]")
	print("Parameters:\n")
	print("-i, --input [folder]         Specify the input folder.")
	print("                             Default is the current folder.\n")
	print("-s, --sort [options]         Sort files into lettered subfolders (A-Z).")
	print("                             Options indicates is special folders should be")
	print("                             also sorted. Can be:")
	print("                             'h' - homebrew")
	print("                             'p' - pirates")
	print("                             'f' - user-defined folders")
	print("                             'a' - all")
	print("                             or use any combinations, like 'hp' or 'ps'.")
	print("                             'reverse' - un-sort ROMs, placing all in the root.\n")
	print("-x, --extract                Extract all 7z/zip files in the folder.\n")
	print("-p, --pack [format]          Pack all files in the folder to 7z/zip format.")
	print("                             [format] can be '7z' or 'zip'. Default is '7z'.\n")
	print("-u, --unlicensed [options]   Disable Homebrew and Pirate stuff separation")
	print("                             to the different folders. [options] can be:")
	print("                             'h' - separate homebrew only")
	print("                             'p' - separate pirates only")
	print("                             'none' - do not separate anything")
	print("                             Separation enabled by default.\n")
	print("-r, --remove-duplicates      Remove duplicate files.")
	print("                             When program stuck with more than one 'best' ROMs:")
	print("                             'ask' - will ask which file to keep.")
	print("                             'all' - will keep all best files.")
	print("                             'one' - will keep only one best file (at random).")
	print("                             If --log, default is 'ask', otherwise 'all'.")
	print("                             --log is recommended for this process.\n")
	print("-f, --folders [list]         Define subfolders to place files, based on tags.\n")
	print("-e, --exclude [list]         Exclude files with specified tags from -f process.\n")
	print("-h, --help                   Show this help message.\n")
	print("-l, --log                    Enable full logging instead of progressbars.\n")
	print("For more details and examples or to support an author,")
	print("please check the README file or visit the GitHub repository:")
	print(f"{Fore.CYAN}https://github.com/ManeFunction/romlm{Style.RESET_ALL}")

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

def process_file(args) -> tuple[str, str]:
	"""Processes a single file for packing or unpacking."""
	file_name, target_folder, is_unpacking_enabled, is_packing_enabled, packing_format = args
	result_log = None
	if is_unpacking_enabled and file_name.endswith((".7z", ".zip")):
		result_log = unpack_file(file_name, target_folder)
	elif is_packing_enabled and not file_name.endswith((".7z", ".zip")) and not file_name.startswith("[BIOS]"):
		result_log = pack_file(file_name, target_folder, packing_format)
	return file_name, result_log

def unpack_file(file_name, target_folder) -> str:
	"""Handles unpacking of a single file."""
	if file_name.endswith(".7z"):
		with py7zr.SevenZipFile(file_name, 'r') as archive:
			archive.extractall(target_folder)
	elif file_name.endswith(".zip"):
		with zipfile.ZipFile(file_name, 'r') as archive:
			archive.extractall(target_folder)
	os.remove(file_name)
	return f" >> Unpacked to: {Fore.BLUE}{target_folder}{Style.RESET_ALL}"

def pack_file(file_name, target_folder, packing_format) -> str:
	"""Handles packing of a single file."""
	archive_path = os.path.join(target_folder, os.path.basename(file_name))
	if packing_format == "7z":
		with py7zr.SevenZipFile(str(archive_path) + ".7z", 'w') as archive:
			archive.write(file_name, arcname=os.path.basename(file_name))
	elif packing_format == "zip":
		with zipfile.ZipFile(str(archive_path + ".zip"), 'w', zipfile.ZIP_DEFLATED) as archive:
			archive.write(file_name, arcname=os.path.basename(file_name))
	os.remove(file_name)
	return f" >> Packed to: {Fore.BLUE}{archive_path}.{packing_format}{Style.RESET_ALL}"

def is_next_optional_parameter(args, i) -> bool:
	return i+1 < len(args) and not args[i+1].startswith("-")

def mane():
	# check for -v or --version argument
	if len(sys.argv) == 2 and sys.argv[1] in ("-v", "--version"):
		print(f"ROMs Library Manager v{version}")
		sys.exit()
	
	# Print welcome message and init variables
	print(f">> Welcome to ROMs Library Manager (v{version})")

	separation_options = CategoryOption.HOMEBREW | CategoryOption.PIRATES
	is_sort_enabled = False
	sort_options = CategoryOption(0)
	is_reverse_sort = False
	is_unpacking_enabled = False
	is_packing_enabled = False
	packing_format = "7z"
	is_log_enabled = False
	is_debug_log = False
	is_remove_duplicates = False
	remove_duplicates_action = duplicates.Action.NOT_DEFINED
	subfolders = None
	exclude_tags = None
	input_folder = "."

	colorama.init()

	# Parse command line arguments
	args = sys.argv[1:]
	skip_next = False
	for i, arg in enumerate(args):
		if skip_next:
			skip_next = False
			continue
		if arg in ("-h", "--help"):
			print_help()
			sys.exit()
		if arg in ("-x", "--extract"):
			is_unpacking_enabled = True
		elif arg in ("-p", "--pack"):
			is_packing_enabled = True
			if is_next_optional_parameter(args, i):
				pack_param = args[i+1]
				if pack_param == "7z":
					packing_format = "7z"
				elif pack_param == "zip":
					packing_format = "zip"
				else:
					print(f"{Fore.RED}Error: Unknown format '{pack_param}'! --pack only supports '7z' or 'zip'.{Style.RESET_ALL}")
					sys.exit(1)
				skip_next = True
		elif arg in ("-u", "--unlicensed"):
			if is_next_optional_parameter(args, i):
				keep_params = args[i+1]
				if keep_params == "none":
					separation_options = CategoryOption(0)
				elif 'a' in keep_params:
					separation_options = CategoryOption.HOMEBREW | CategoryOption.PIRATES
				else:
					if 'h' in keep_params:
						separation_options |= CategoryOption.HOMEBREW
					if 'p' in keep_params:
						separation_options |= CategoryOption.PIRATES
				skip_next = True
		elif arg in ("-s", "--sort"):
			is_sort_enabled = True
			if is_next_optional_parameter(args, i):
				sort_params = args[i+1]
				if sort_params == "reverse":
					is_reverse_sort = True
				else:
					if sort_params == "none":
						sort_options = CategoryOption(0)
					elif 'a' in sort_params:
						sort_options = CategoryOption.HOMEBREW | CategoryOption.PIRATES | CategoryOption.SUBFOLDERS
					else:
						if 'h' in sort_params:
							sort_options |= CategoryOption.HOMEBREW
						if 'p' in sort_params:
							sort_options |= CategoryOption.PIRATES
						if 'f' in sort_params:
							sort_options |= CategoryOption.SUBFOLDERS
				skip_next = True
		elif arg in ("-l", "--log"):
			is_log_enabled = True
		elif arg == "--debug":
			is_debug_log = True
		elif arg in ("-r", "--remove-duplicates"):
			is_remove_duplicates = True
			if is_next_optional_parameter(args, i):
				remove_duplicates_param = args[i+1]
				if remove_duplicates_param == "ask":
					remove_duplicates_action = duplicates.Action.ASK
				elif remove_duplicates_param == "all":
					remove_duplicates_action = duplicates.Action.KEEP_ALL
				elif remove_duplicates_param == "one":
					remove_duplicates_action = duplicates.Action.KEEP_ONE
				else:
					print(f"{Fore.RED}Error: Unknown action '{remove_duplicates_param}'! --remove-duplicates only supports 'ask', 'all' or 'one'.{Style.RESET_ALL}")
					sys.exit(1)
				skip_next = True
		elif arg in ("-f", "--folders"):
			if i+1 < len(args):
				subfolders = args[i+1].split(",")
				if is_log_enabled:
					print("Subfolders:", subfolders)
				skip_next = True
			else:
				print(f"{Fore.RED}Error: --subfolders requires a comma-separated list of subfolders.{Style.RESET_ALL}")
				sys.exit(1)
		elif arg in ("-e", "--exclude"):
			if i+1 < len(args):
				exclude_tags = args[i+1].split(",")
				if is_log_enabled:
					print("Exclude tags:", exclude_tags)
				skip_next = True
			else:
				print(f"{Fore.RED}Error: --exclude requires a comma-separated list of tags.{Style.RESET_ALL}")
				sys.exit(1)
		elif arg in ("-i", "--input"):
			if i+1 < len(args):
				input_folder = args[i+1]
				skip_next = True
			else:
				print(f"{Fore.RED}Error: --input requires a folder path.{Style.RESET_ALL}")
				sys.exit(1)
				
	# Set default action for duplicates removal
	if remove_duplicates_action == duplicates.Action.NOT_DEFINED:
		remove_duplicates_action = duplicates.Action.ASK if is_log_enabled else duplicates.Action.KEEP_ALL

	# Check for conflicting options
	if is_unpacking_enabled is True and is_packing_enabled is True:
		print(f"{Fore.RED}Error: You cannot --extract and --pack at the same time.{Style.RESET_ALL}")
		sys.exit(1)

	if (is_sort_enabled is False
			and is_unpacking_enabled is False
			and is_packing_enabled is False
			and is_remove_duplicates is False):
		print(f"{Fore.YELLOW}Nothing to do...{Style.RESET_ALL}")
		sys.exit()

	if not os.path.exists(input_folder):
		print(f"{Fore.RED}Error: The specified input folder '{input_folder}' does not exist.{Style.RESET_ALL}")
		sys.exit(1)
	os.chdir(input_folder)
	print(f"Current working directory set to: {os.getcwd()}")

	if exclude_tags is not None and subfolders is None:
		print(f"{Fore.YELLOW}Warning: You cannot use --exclude without --subfolders. Option ignored.{Style.RESET_ALL}")

	# Get files list
	files_list = glob.glob("**/*.*", recursive=True)

	# If duplicates removal is enabled, do it first
	if is_remove_duplicates:
		files_was = len(files_list)
		files_list = duplicates.clean_duplicates(files_list, remove_duplicates_action, is_log_enabled, is_debug_log)
		if files_was != len(files_list):
			print(f"Total ROMs left after duplicates removal: {Fore.GREEN}{len(files_list)}{Style.RESET_ALL} "
				  f"out of {Fore.RED}{files_was}{Style.RESET_ALL}")
		else:
			print("No duplicates found...")
		
	def get_target_folder() -> str:
		if is_sort_enabled:
			if is_reverse_sort:
				return '.'
			return get_new_folder(os.path.basename(file_name), separation_options, sort_options,
										   subfolders, exclude_tags)
		return os.path.dirname(file_name)
		
	# Process files
	if is_sort_enabled is True or is_unpacking_enabled is True or is_packing_enabled is True:
		# Single-threaded processing for just a move operation
		if not is_unpacking_enabled and not is_packing_enabled:
			print(">> Processing files...")
			progress = files_list if is_log_enabled else tqdm(files_list, desc="Processing")
			
			for file_name in progress:
				target_folder = get_target_folder()
				shutil.move(file_name, os.path.join(target_folder, os.path.basename(str(file_name))))
				if is_log_enabled:
					print(f" >> Moved to: {Fore.BLUE}{target_folder}{Style.RESET_ALL}")
		else:
			# Multithreaded processing for packing/unpacking
			print(">> Preparing processing...")
			tasks = []
			for file_name in files_list:
				target_folder = get_target_folder()
				tasks.append((file_name, target_folder, is_unpacking_enabled, is_packing_enabled, packing_format))
				
			print(">> Processing files...")
			i = 0
			if is_log_enabled:
				with Pool(processes=os.cpu_count()) as pool:
					for task in pool.imap_unordered(process_file, tasks):
						i += 1
						f_name, result_log = task
						print(f"({i}/{len(tasks)}) Processed: {Fore.GREEN}{f_name}{Style.RESET_ALL}")
						if result_log is not None:
							print(result_log)
			else:
				with Pool(processes=os.cpu_count()) as pool:
					with tqdm(total=len(tasks), desc="Processing") as progress:
						for _ in pool.imap_unordered(process_file, tasks):
							progress.update(1)
					
	
		remove_meta_files(".", is_log_enabled)
		remove_empty_subfolders(".", is_log_enabled)

	print(">> DONE!")
	sys.exit()

if __name__ == "__main__":
	freeze_support()
	mane()
