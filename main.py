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
		
def get_lettered_folder_name(filename) -> str:
	folder_name = filename[0].upper() if filename else ''
	if folder_name == "[":
		folder_name = "!!BIOS"
	elif not folder_name.isalpha():
		folder_name = "1-9"
	return folder_name

def try_add_subfolder(is_sort_subfolders, folder_name, filename) -> str:
	return (folder_name + "/" + get_lettered_folder_name(filename)) if is_sort_subfolders else folder_name

def get_new_folder(filename, is_sort_homebrew, is_sort_subfolders, subfolders) -> str:
	file_name_lower = filename.lower()
	if 'homebrew' in file_name_lower or 'aftermarket' in file_name_lower:
		folder_name = try_add_subfolder(is_sort_homebrew, "!Homebrew", filename)
	elif subfolders is not None:
		found_subfolder = ""
		for subfolder in subfolders:
			if subfolder.lower() in file_name_lower:
				found_subfolder = "!" + subfolder
				break
		folder_name = try_add_subfolder(is_sort_subfolders, found_subfolder, filename) \
			if found_subfolder != "" \
			else get_lettered_folder_name(filename)
	else:
		folder_name = get_lettered_folder_name(filename)
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
	is_sort_homebrew = False
	is_sort_subfolders = False
	is_reverse_sort = False
	is_unpacking_enabled = False
	is_packing_enabled = False
	packing_format = "7z"
	is_log_enabled = False
	is_remove_duplicates = False
	subfolders = None
	input_folder = "."

	args = sys.argv[1:]
	skip_next = False
	for i, arg in enumerate(args):
		if skip_next:
			skip_next = False
			continue
		if arg in ("-u", "--unpack"):
			is_unpacking_enabled = True
		elif arg in ("-p", "--pack"):
			is_packing_enabled = True
			if i+1 < len(args) and not args[i+1].startswith("-"):
				pack_param = args[i+1]
				if pack_param == "7z":
					packing_format = "7z"
				elif pack_param == "zip":
					packing_format = "zip"
				else:
					print(f"Error: Unknown format '{pack_param}'! --pack only supports '7z' or 'zip'.")
					sys.exit(1)
				skip_next = True
		elif arg in ("-s", "--sort"):
			is_sort_enabled = True
			if i+1 < len(args):
				sort_param = args[i+1]
				if sort_param == "reverse":
					is_reverse_sort = True
				else:
					is_sort_homebrew = sort_param in ("all", "homebrew")
					is_sort_subfolders = sort_param in ("all", "subfolders")
				skip_next = True
		elif arg in ("-l", "--log"):
			is_log_enabled = True
		elif arg in ("-r", "--remove-duplicates"):
			is_remove_duplicates = True
		elif arg in ("-f", "--subfolders"):
			if i+1 < len(args):
				subfolders = args[i+1].split(",")
				if is_log_enabled:
					print("Subfolders:", subfolders)
				skip_next = True
			else:
				print("Error: --subfolders requires a comma-separated list of subfolders.")
				sys.exit(1)
		elif arg in ("-i", "--input"):
			if i+1 < len(args):
				input_folder = args[i+1]
				skip_next = True
			else:
				print("Error: --input requires a folder path.")
				sys.exit(1)

	if is_unpacking_enabled is True and is_packing_enabled is True:
		print("Error: You cannot --extract and --pack at the same time.")
		sys.exit()

	if (is_sort_enabled is False
			and is_unpacking_enabled is False
			and is_packing_enabled is False
			and is_remove_duplicates is False):
		print("Nothing to do...")
		sys.exit()

	if not os.path.exists(input_folder):
		print(f"Error: The specified input folder '{input_folder}' does not exist.")
		sys.exit(1)
	os.chdir(input_folder)
	print(f"Current working directory set to: {os.getcwd()}")

	# Get files list
	files_list = glob.glob("**/*.*", recursive=True)

	# If duplicates removal is enabled, do it first
	if is_remove_duplicates:
		files_list = clean_duplicates(files_list, is_log_enabled)
		print("Total ROMs after duplicates removal: ", len(files_list))
		
	# Process files
	if is_sort_enabled is True or is_unpacking_enabled is True or is_packing_enabled is True:
		print(">> Processing files...")
		if is_log_enabled:
			progress = files_list
		else:
			progress = tqdm(files_list, desc="Processing")
	
		for file_name in progress:
			if is_log_enabled:
				print("Processing:" + file_name)
	
			# Sorting options
			if is_sort_enabled:
				if is_reverse_sort:
					target_folder = '.'
				else:
					target_folder = get_new_folder(os.path.basename(file_name), is_sort_homebrew, is_sort_subfolders, subfolders)
			else:
				target_folder = os.path.dirname(file_name)
	
			# Extracting block
			if is_unpacking_enabled:
				if file_name.endswith(".7z"):
					with py7zr.SevenZipFile(file_name, 'r') as archive:
						archive.extractall(target_folder)
				elif file_name.endswith(".zip"):
					with zipfile.ZipFile(file_name, 'r') as archive:
						archive.extractall(target_folder)
				os.remove(file_name)
			# Packing block
			elif is_packing_enabled and not file_name.endswith(".7z") and not file_name.endswith(".zip"):
				if is_log_enabled:
					print("Packing:", file_name)
				if packing_format == "7z":
					with py7zr.SevenZipFile(file_name + ".7z", 'w') as archive:
						archive.write(file_name, arcname=os.path.basename(file_name))
				elif packing_format == "zip":
					with zipfile.ZipFile(file_name + ".zip", 'w', zipfile.ZIP_DEFLATED) as archive:
						archive.write(file_name, arcname=os.path.basename(file_name))
				os.remove(file_name)
			# Execute sorting
			else:
				shutil.move(file_name, os.path.join(target_folder, os.path.basename(str(file_name))))
	
		remove_empty_subfolders(".", is_log_enabled)

	print(">> DONE!")
	sys.exit()

if __name__ == "__main__":
	freeze_support()
	Process(target=mane).start()
