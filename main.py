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
def get_new_folder(file_name) -> str:
	file_name_lower = file_name.lower()
	if 'aftermarket' in file_name_lower:
		target_folder = "!Aftermarket"
	elif 'homebrew' in file_name_lower:
		target_folder = "!Homebrew"
	else:
		target_folder = file_name[0].upper()
		if target_folder == "[":
			target_folder = "!BIOS"
		elif not target_folder.isalpha():
			target_folder = "1-9"
	create_if_not_exist(target_folder)
	return target_folder


# main codeblock declaration to be able to use arguments
if __name__ == "__main__":
	# set up parameters, check input arguments
	isSortEnabled = True
	isExtractEnabled = True
	isDeleteEnabled = True
	for arg in sys.argv:
		if arg == "--nosort":
			isSortEnabled = False
		elif arg == "--noextract":
			isExtractEnabled = False
		elif arg == "--nodelete":
			isDeleteEnabled = False

	# nothing to do?
	if isSortEnabled is False and isExtractEnabled is False:
		print("Nothing to do...")
		exit()

	# get files list and iterate it with progress bar
	filesList = glob.glob("*.zip") + glob.glob("*.7z")
	total = len(filesList)
	print("Total files found: " + str(total))
	for i in tqdm(range(total)):
		fileName = filesList[i]
		# sorting option
		if isSortEnabled:
			targetFolder = get_new_folder(fileName)
		else:
			targetFolder = './'
		# extracting option
		if isExtractEnabled:
			if fileName.endswith(".7z"):
				with py7zr.SevenZipFile(fileName, 'r') as archive:
					archive.extractall(targetFolder)
			elif fileName.endswith(".zip"):
				with zipfile.ZipFile(fileName, 'r') as archive:
					archive.extractall(targetFolder)
			if isDeleteEnabled:
				os.remove(fileName)
		else:
			shutil.move(fileName, os.path.join(targetFolder, fileName))
	print("DONE!")

