import os
import glob
import patoolib
import py7zr
from tqdm import tqdm

filesList = glob.glob('*.7z')
total = len(filesList)
for i in tqdm(range(total)):
	fileName = filesList[i]
	folder = fileName[0].upper()
	if not folder:
		os.makedirs(folder)
	with py7zr.SevenZipFile(fileName, 'r') as archive:
		archive.extractall(folder + '/')
	os.remove(fileName)