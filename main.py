import sys
import os
import re
import shutil
import glob
import py7zr
import zipfile
from tqdm import tqdm
from multiprocessing import Process, freeze_support

def create_if_not_exist(folder):
	if not os.path.exists(folder):
		os.makedirs(folder)

def get_new_folder(filename) -> str:
	file_name_lower = filename.lower()
	if 'aftermarket' in file_name_lower:
		folder_name = "!Aftermarket"
	elif 'homebrew' in file_name_lower:
		folder_name = "!Homebrew"
	else:
		folder_name = filename[0].upper() if filename else ''
		if folder_name == "[":
			folder_name = "!!BIOS"
		elif not folder_name.isalpha():
			folder_name = "1-9"
	create_if_not_exist(folder_name)
	return folder_name

def remove_empty_subfolders(path, is_log_enabled):
	# Walk through the directory tree from the bottom up
	for dirpath, dirnames, filenames in os.walk(path, topdown=False):
		# If there are no files and no subdirectories, remove this directory
		if not dirnames and not filenames:
			# Make sure we don't remove the root directory itself if that's not desired
			if dirpath != path:
				os.rmdir(dirpath)
				if is_log_enabled:
					print(f"Removed empty folder: {dirpath}")

def get_base_name(filename: str) -> str:
	name_no_ext = os.path.splitext(filename)[0]
	idx = name_no_ext.find('(')
	if idx != -1:
		base = name_no_ext[:idx].strip()
	else:
		base = name_no_ext.strip()
	return base

def is_pure_region(fname, region):
	name_no_ext = os.path.splitext(fname)[0]
	groups = re.findall(r'\(.*?\)', name_no_ext)
	return len(groups) == 1 and groups[0] == f"({region})"

def try_keep_pure_region(paths, region, files_to_keep, is_log_enabled):
	# Try to find a pure region file for the given region, keep one, remove others.
	# Returns True if a pure region file was found and handled, otherwise False.
	pure_region_files = [p for p in paths if is_pure_region(os.path.basename(p), region)]
	if pure_region_files:
		keep = pure_region_files[0]
		files_to_keep.add(keep)
		for p in paths:
			if p != keep:
				if is_log_enabled:
					print(f"Removing: {os.path.basename(p)}")
				os.remove(p)
		return True
	return False

def clean_duplicates(file_list, is_log_enabled):
	file_list = list(file_list)
	
	by_basename = {}
	for f in file_list:
		fname = os.path.basename(f)
		base = get_base_name(fname)
		if base not in by_basename:
			by_basename[base] = []
		by_basename[base].append(f)

	print(">> Removing duplicates safely... \nTotal ROMs:", len(file_list), "\nActual games:", len(by_basename))

	files_to_keep = set()
	regions_priority = ["World", "USA", "Europe", "Japan"]

	if is_log_enabled:
		progress = by_basename.items()
	else:
		progress = tqdm(by_basename.items(), desc="Cleaning Duplicates", total=len(by_basename))

	for base, paths in progress:
		if len(paths) > 1:
			# Try each region in priority order
			found = False
			for region in regions_priority:
				if try_keep_pure_region(paths, region, files_to_keep, is_log_enabled):
					found = True
					break

			if not found:
				# Neither USA, Europe nor Japan pure versions found
				if is_log_enabled:
					print(f"Warning: Cannot decide which file to keep for base name '{base}':")
				for p in paths:
					if is_log_enabled:
						print(" - ", os.path.basename(p))
					files_to_keep.add(p)
		else:
			files_to_keep.add(paths[0])

	return [f for f in file_list if f in files_to_keep]

def mane():
	print(">> Initializing...")

	is_sort_enabled = False
	is_reverse_sort = False
	is_extract_enabled = False
	is_delete_enabled = True
	is_log_enabled = False
	is_remove_duplicates = False
	input_folder = "."

	args = sys.argv[1:]
	skip_next = False
	for i, arg in enumerate(args):
		if skip_next:
			skip_next = False
			continue
		if arg in ("-e", "--extract"):
			is_extract_enabled = True
		elif arg in ("-s", "--sort"):
			is_sort_enabled = True
			if i+1 < len(args) and args[i+1] == "reverse":
				is_reverse_sort = True
				skip_next = True
		elif arg in ("-k", "--keep"):
			is_delete_enabled = False
		elif arg in ("-l", "--log"):
			is_log_enabled = True
		elif arg in ("-r", "--remove-duplicates"):
			is_remove_duplicates = True
		elif arg in ("-i", "--input"):
			if i+1 < len(args):
				input_folder = args[i+1]
				skip_next = True
			else:
				print("Error: --input requires a folder path.")
				sys.exit(1)

	if not os.path.exists(input_folder):
		print(f"Error: The specified input folder '{input_folder}' does not exist.")
		sys.exit(1)
	os.chdir(input_folder)
	print(f"Current working directory set to: {os.getcwd()}")

	if is_sort_enabled is False and is_extract_enabled is False and is_remove_duplicates is False:
		print("Nothing to do...")
		sys.exit()

	# Get files list
	if is_extract_enabled:
		files_list = glob.glob("**/*.zip", recursive=True) + glob.glob("**/*.7z", recursive=True)
	else:
		files_list = glob.glob("**/*.*", recursive=True)

	# If duplicates removal is enabled, do it first
	if is_remove_duplicates:
		files_list = clean_duplicates(files_list, is_log_enabled)
		print("Total ROMs after duplicates removal: ", len(files_list))
		
	# Process files
	if is_sort_enabled is True or is_extract_enabled is True:
		print(">> Processing files...")
		if is_log_enabled:
			progress = files_list
		else:
			progress = tqdm(files_list, desc="Processing")
	
		for file_name in progress:
			if is_log_enabled:
				print("Processing:" + file_name)
	
			# Sorting option
			if is_sort_enabled:
				if is_reverse_sort:
					target_folder = '.'
				else:
					target_folder = get_new_folder(file_name)
			else:
				target_folder = './'
	
			# Extracting option
			if is_extract_enabled:
				if file_name.endswith(".7z"):
					with py7zr.SevenZipFile(file_name, 'r') as archive:
						archive.extractall(target_folder)
				elif file_name.endswith(".zip"):
					with zipfile.ZipFile(file_name, 'r') as archive:
						archive.extractall(target_folder)
				if is_delete_enabled:
					os.remove(file_name)
			else:
				shutil.move(file_name, os.path.join(target_folder, os.path.basename(file_name)))
	
		if is_sort_enabled and is_reverse_sort:
			remove_empty_subfolders(".", is_log_enabled)

	print(">> DONE!")
	sys.exit()

if __name__ == "__main__":
	freeze_support()
	Process(target=mane).start()
