import sys
import os
import glob
from tqdm import tqdm
from multiprocessing import Process, freeze_support

def mane():
	print(">> Initializing...")

	input_folder = "."

	# Parse arguments
	args = sys.argv[1:]
	skip_next = False
	for i, arg in enumerate(args):
		if skip_next:
			skip_next = False
			continue
		if arg in ("-i", "--input"):
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

	# Get files list
	files_list = glob.glob("**/*.*", recursive=True)
		
	# Process files
	print(">> Processing files...")

	with open("output.txt", "w") as out:
		for file_name in tqdm(files_list, desc="Processing"):
			file_size = os.path.getsize(file_name)
			out.write(f"{file_name} - {file_size}\n")

	print(">> DONE!")
	sys.exit()

if __name__ == "__main__":
	freeze_support()
	Process(target=mane).start()
