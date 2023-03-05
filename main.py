import sys
import os
import shutil
import glob
import py7zr
import zipfile
from tqdm import tqdm


# define the method that check if file exists and create it if it doesn't
def create_if_not_exist(folder):
	if not os.path.exists(folder):
		os.makedirs(folder)


# define the method that get a specific folder name based on sorting needs
def get_new_folder(filename) -> str:
	file_name_lower = filename.lower()
	if 'aftermarket' in file_name_lower:
		targetfolder = "!Aftermarket"
	elif 'homebrew' in file_name_lower:
		targetfolder = "!Homebrew"
	else:
		targetfolder = filename[0].upper()
		if targetfolder == "[":
			targetfolder = "!BIOS"
		elif not targetfolder.isalpha():
			targetfolder = "1-9"
	create_if_not_exist(targetfolder)
	return targetfolder


# main codeblock declaration to be able to use arguments
if __name__ == "__main__":
	# set up parameters, check input arguments
	is_sort_enabled = True
	is_extract_enabled = True
	is_delete_enabled = True
	is_filename_enabled = False
	for arg in sys.argv:
		if arg == "--nosort":
			is_sort_enabled = False
		elif arg == "--noextract":
			is_extract_enabled = False
		elif arg == "--nodelete":
			is_delete_enabled = False
		elif arg == "--filename":
			is_filename_enabled = True

	# nothing to do?
	if is_sort_enabled is False and is_extract_enabled is False:
		print("Nothing to do...")
		exit()

	# get files list and iterate it with progress bar
	files_list = glob.glob("*.zip") + glob.glob("*.7z")
	progress = tqdm(files_list)
	for file_name in progress:
		# set progress bar description
		if is_filename_enabled:
			progress.set_description(file_name)
		# sorting option
		if is_sort_enabled:
			target_folder = get_new_folder(file_name)
		else:
			target_folder = './'
		# extracting option
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
			shutil.move(file_name, os.path.join(target_folder, file_name))
	print("DONE!")

