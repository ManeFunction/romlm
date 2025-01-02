# romlm

A Python-based command line tool that helps you organize and manage your ROM collections effortlessly. 
Whether you want to pack, unpack, sort, or remove duplicates, **romlm** has got you covered.

All features are tested on the no-intro ROM sets (which I personally recommend), but it should work with any 
ROM collection that follows a similar naming convention.
If you have some issues with other ROM sets, that can't be worked-around with the current implementation, 
feel free to open an issue on the [GitHub issues](https://github.com/ManeFunction/roms-library-manager/issues) page.

---

## Features

- **Extract (`-x, --extract`)**  
  Automatically unpacks all `.7z` or `.zip` files in the current directory (or a specified folder) into subfolders. 
  Supports nested subfolders, keeping all the structure.

  ![](https://raw.githubusercontent.com/wiki/ManeFunction/roms-library-manager/extract.png)


- **Pack (`-p, --pack`)**  
  Compresses all uncompressed files in the current directory (or a specified folder) into `.7z` or `.zip` archives. 
  Supports nested subfolders, keeping all the structure.

  ![](https://raw.githubusercontent.com/wiki/ManeFunction/roms-library-manager/pack.png)


- **Sort (`-s, --sort`)**  
  Moves files into alphabetically organized subfolders (A–Z). Optionally handles special folders for 
  Homebrew (`!Homebrew`), Pirates (`!Pirates`), or user-defined subfolders (`-f`).
    - `h` will also sort files into homebrew subfolder.
    - `p` will also sort files into pirates subfolder.
    - `f` will also sort files into user-defined subfolders (`-f`).
    - `a` will also sort files into homebrew, pirates and all user-defined subfolders (`-f`). Equal to `hpf`.
    - You can also use any combination of `h`, `p` and `f` options, for example `hp` or `fh`.
    - `-s reverse` will reverse-sort files, i.e., move them all back into the root folder.
  
  ![](https://raw.githubusercontent.com/wiki/ManeFunction/roms-library-manager/sort.png)


- **Separate Homebrew and Pirate ROMs (`-u, --unlicensed`)**  
  By default, romlm detects and separates Homebrew or Pirate files into dedicated folders. Can be customized with 
  options:
    - `none` disables separation completely,
    - `h` separates Homebrew files only,
    - `p` separates Pirate files only.

  ![](https://raw.githubusercontent.com/wiki/ManeFunction/roms-library-manager/unlicensed.png)


- **Remove Duplicates (`-r, --remove-duplicates`)**  
  Automatically detects duplicate files, preserving the best candidate according
  to region, beta status, revision, version, release date and other data that can be received from the filename.
  Behavior for the situations when script can't decide the best file itself, can be specified:
    - `ask` prompts you which file to keep, default with `-l`,
    - `all` keeps all equally good files, default without `-l`,
    - `one` keeps exactly one of the best ROMs, taken randomly.

  I highly recommend to **use this feature with `-l` option** to see the results, and **make a backup of your ROMs before**!
  
  In the current scenario it removes all the beta and prototype files if there is a final version of the game exists. 
  If not, it tries to keep only one the latest version. USA retro ROMs (not Virtual Console versions) counts as 
  the best version of the game. Also, Europe and EN releases have a higher priority over JP and Asia versions, 
  as well as NTSC counts better, than PAL. **romlm** will never remove all copies of one game!
  
  If you want to keep a Japanese collection intact, I recommend to separate it first. See Usage Examples below.
      
  ![](https://raw.githubusercontent.com/wiki/ManeFunction/roms-library-manager/remove.png)


- **User-defined Folders (`-f, --folders`)**  
  Easily map certain tags to user-defined folders. For example, specifying `-f Japan` will move ROMs tagged 
  as `(Japan)` into dedicated subfolder. Works only with `--sort` process as a part of it. Search only within tags, 
  to not be confused with a game name, so if you just want all your Mario games in one place, just search it manually, 
  **romlm** not for that.

- **Exclude Tags (`-e, --exclude`)**  
  Combine with `-f` to skip specified tags from the subfolders sorting process. For example, `-f Japan -e USA`
  will move all `(Japan)` tagged ROMs into a dedicated subfolder, excluding any `(USA)` tagged ROMs
  if `(Japan, USA)` combination is met.

  ![](https://raw.githubusercontent.com/wiki/ManeFunction/roms-library-manager/subfolder.png)


- **Logging (`-l, --log`)**  
  Enables verbose output to see exactly what the script is doing. Extremely useful when `--remove-duplicates` is enabled.

  ![](https://raw.githubusercontent.com/wiki/ManeFunction/roms-library-manager/remove-log.png)


- **Other Utilities**  
    - Cleans out unwanted system meta-files (e.g., `desktop.ini`, `.DS_Store`).
    - Removes empty subdirectories after sorting.
    - Provides an in-script help guide (`-h, --help`).

---

## Usage examples and backstory

As a user of Analogue Pocket and an Emulation Station based handheld system, there are some nuances from both worlds 
that I'm trying to cover with **romlm**. Analogue Poket is a highly precise FPGA-based console, but it covers only
earlier generations and a scoop of Arcade games. Though, those platforms, like NES, SNES and Genesis have a huge
library of games, that should be sorted to have an easy access. Also, Pocket do not support archives, so all the ROMs
should be unpacked. Standard software emulators, on the other hand, can play archived ROMs, and with the support 
of more later platforms, where games became bigger, it's great to have them packed, but also, it's good to have 
old systems packed as well, to save some Gigs for a few more CD games. So, I've need a tool to prepare my ROMs 
for both systems in a few clicks. That's how **romlm** was born.


Personally, I keep all my ROMs on Analogue Pocket, to be able to quickly launch any version of any game it supports. 
But I do not need all of those for a device that made for casual play. To be honest, I have Powkidy RGB30 with 
a rectangular screen, specifically for the Pico-8. Emulation capabilities of this device is just a neat bonus 
for me :) So, to prepare ROMs for Emulation Station devices, like Powkiddy, Anbernic, Miyoo, etc. we can clean 
our library from all the stuff we never play anyway. 


There is an example how to separate and work with your Japanese library, if you need it. But it also can be a great
example of **romlm** capabilities for you to learn. Emulation Station have a separate folders for Japanese libraries 
(at least for the 3 whales of retro gaming: NES, SNES and Genesis) as well as for homebrew, 
so it's good to separate them first, if you are interested in them. Here is the way:
1) `-i ./your-roms -s a -f Japan -e USA,EN` command first to separate non-en Japanese releases 
(they ends up in `!Japan` folder). Alternatively, you can use `-s f` if your collection do not have a lot of homebrew
and pirates, and you do not need to sort them in (A-Z) folders.
1) Put all sorted folders (A-Z) from `your-roms` folder to `your-roms/sorted` for example, to be able to treat them
separately later.
1) Now you should have `sorted`, `!Japan`, `!Homebrew` (if there was any) and `!Pirates` (if there was any) 
folders in your `your-roms` folder. `!` is used here to keep them on top of the list, as Emulation Station sorts
folders alphabetically, but remember, that you should escape it with `\!` in the command line, so path 
for the next commands should look like `-i ./your-roms/\!Japan` for example.
1) Do `-i ./your-roms/sorted -r -l` for all the subfolders separately to remove duplicates, but keep them in 
sorted (mostly USA for now) and Japanese folders.
1) After that you can pack all the ROMs in one command `-i ./your-roms -p`. This command keeps our new folders structure.

This way you will keep all the Japanese versions of the games, separated into a dedicated folder, and anyways
all other duplicates will be removed, easing the access to the games you want to play in the future and
saving the space on your device for more great games.


---

## Installation

**romlm** is available to use in a variety of ways.
<!-- 1) **brew (Recommended for Mac users)**
    - You can install **rolm** through the [Homebrew](https://brew.sh/) formula for macOS users (if you have **brew** installed), 
      typing `brew install romlm` in the Terminal. -->
1) **Ready to use binaries (Mac and Windows)**
    - Download ready-to-use binaries from the [GitHub Releases](https://github.com/ManeFunction/roms-library-manager/releases).  
1) **Python script**
    - if you know how to work with Python scripts, venv, and dependencies, you can simply clone the repository 
      and run `romlm.py`. In that way, feel free to modify the script for yourself as you want.

---

## Credits

Created and maintained by ManeFunction.

Thanks for your contributions and feedback!
If you have any questions, suggestions, or issues, feel free to open an issue on the [GitHub issues](https://github.com/ManeFunction/roms-library-manager/issues) page 
or create a or pull request.