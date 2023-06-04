import sys
import os
import shutil
import glob
import py7zr
import zipfile
from tqdm import tqdm
from multiprocessing import Process, freeze_support


# define the method that check if file exists and create it if it doesn't
def create_if_not_exist(folder):
	if not os.path.exists(folder):
		os.makedirs(folder)


# define the method that get a specific folder name based on sorting needs
def get_new_folder(filename) -> str:
	file_name_lower = filename.lower()
	if 'aftermarket' in file_name_lower:
		folder_name = "!Aftermarket"
	elif 'homebrew' in file_name_lower:
		folder_name = "!Homebrew"
	else:
		folder_name = filename[0].upper()
		if folder_name == "[":
			folder_name = "!!BIOS"
		elif not folder_name.isalpha():
			folder_name = "1-9"
	create_if_not_exist(folder_name)
	return folder_name


# main codeblock
def mane():
	# set execution path to script's folder
	os.chdir(os.path.dirname(os.path.abspath(sys.executable)))
	print("Current working directory: ", os.getcwd())
	# set up parameters, check input arguments
	is_sort_enabled = True
	is_extract_enabled = True
	is_delete_enabled = True
	is_log_enabled = False
	for arg in sys.argv:
		if arg == "-e" or arg == "--extract":
			is_sort_enabled = False
		elif arg == "-s" or arg == "--sort":
			is_extract_enabled = False
		elif arg == "-k" or arg == "--keep":
			is_delete_enabled = False
		elif arg == "-l" or arg == "--log":
			is_log_enabled = True

	# nothing to do?
	if is_sort_enabled is False and is_extract_enabled is False:
		print("Nothing to do...")
		sys.exit()

	# get files list and iterate it with progress bar
	if is_extract_enabled:
		files_list = glob.glob("*.zip") + glob.glob("*.7z")
	else:
		files_list = glob.glob("*.*")
		files_list = [file for file in files_list if not file.endswith(".py")]
	if is_log_enabled:
		progress = files_list
	else:
		progress = tqdm(files_list)
	for file_name in progress:
		if is_log_enabled:
			print("Processing: " + file_name)
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
	sys.exit()


# main method declaration to be able to use arguments
# and prevent compiled executable from getting stuck in the infinite loop
if __name__ == "__main__":
	print("\nWelcome to the ROMs sorter by Mane Function!\nInitializing...")
	freeze_support()
	Process(target=mane).start()
