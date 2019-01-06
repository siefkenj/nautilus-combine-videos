# nautilus-combine-videos
Nautilus script to combine multiple video files with sensible defaults

## Usage
Add the script to

    ~/.local/share/nautilus/scripts/
 
Then, right-click on a collection of video files and enjoy!
  
## Requirements
This is a python 3 script that uses the `natsort` package to alphabetize files 
in a human-sensible way before encoding. The user-input dialog is created using `zenity`.
All encoding is done with `ffmpeg` Files are output using `libx264` for video and `aac`
for audio.
