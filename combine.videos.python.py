#!/usr/bin/python3
# combine video files in a semi-intelligent way

import os
import sys
import subprocess
import json
from functools import reduce
from math import sqrt
import random
from fractions import Fraction
import urllib, urllib.parse

try:
    import natsort
    versort = natsort.natsorted
except:
    versort = lambda x: list(sorted(x))


def get_streams(lst):
    """ return the first video and audio streams in the file """
    video,audio = {},{}
    for s in reversed(lst):
        if s.get('codec_type', False) == 'video':
            video = s
        if s.get('codec_type', False) == 'audio':
            audio = s
    return (video, audio)

def get_optimal_size(sizes):
    """ takes in an array of tuples (width,height)
    and outputs the (width,height) pair closest to the average """

    sums = reduce(lambda a,b: (a[0]+b[0], a[1]+b[1]), sizes)
    ave = (sums[0]/len(sizes), sums[1]/len(sizes))

    def dist_to_ave(a):
        return sqrt((a[0]-ave[0])**2 + (a[1]-ave[1])**2)

    dists = [dist_to_ave(a) for a in sizes]
    size_index = dists.index(min(dists))

    return sizes[size_index]

def get_rotated_width_height(width, height, vid_info):
    try:
        angle = vid_info["tags"]["rotate"]
        angle = int(angle) % 180

        if angle > 0:
            # in this case, we are rotated by +-90 degrees
            return (height, width)
    except KeyError:
        pass
    
    return (width, height)

def get_optimal_fps(fps_list):
    return max(fps_list)

if __name__ == "__main__":
    # get all the nautilus environmental variables
    NAUTILUS_SCRIPT_CURRENT_URI = os.environ.get('NAUTILUS_SCRIPT_CURRENT_URI', "")
    NAUTILUS_SCRIPT_SELECTED_FILE_PATHS = os.environ.get('NAUTILUS_SCRIPT_SELECTED_FILE_PATHS', "")
    NAUTILUS_SCRIPT_SELECTED_URIS = os.environ.get('NAUTILUS_SCRIPT_SELECTED_URIS', "")
    NAUTILUS_SCRIPT_WINDOW_GEOMETRY = os.environ.get('NAUTILUS_SCRIPT_WINDOW_GEOMETRY', "")

    video_files = [f.strip() for f in NAUTILUS_SCRIPT_SELECTED_FILE_PATHS.split('\n') if f.strip() != ""]
    video_files = versort(video_files)

    print("Processing video files \n\n{}\n\n".format(video_files))

    processing_info = []

    # get stats on each video file
    INFO_COMMAND = "ffprobe -v quiet -print_format json -show_format -show_streams".split(" ")
    for i,f in enumerate(video_files):
        processing_info.append({'filename': f})
        try:
            info = subprocess.check_output(INFO_COMMAND + [f], universal_newlines=True)
            info = json.loads(info)
            #processing_info[-1]['all_info'] = info
            print(info)

            # get the video information
            video,audio = get_streams(info['streams'])
            # the video could be rotated. If so, we need to swap the width and height as appropriate.
            width, height = get_rotated_width_height(video['coded_width'], video['coded_height'], video)
            processing_info[-1]['width'] = width
            processing_info[-1]['height'] = height
            processing_info[-1]['fps'] = Fraction(video['avg_frame_rate'])

        except subprocess.CalledProcessError:
            pass

    sizes = [(a['width'], a['height']) for a in processing_info]
    optimal_size = list(get_optimal_size(sizes))
    fpss = [a['fps'] for a in processing_info]
    optimal_fps = get_optimal_fps(fpss)

    # get some user input on the file name
    QUERY_COMMAND = ["zenity", '--title=Combine Videos', "--forms",
            "--text={} files at size {} and fps {}".format(len(sizes), optimal_size, round(float(optimal_fps), 4)),
            "--add-entry=Output:",
            "--add-entry=Override Width ({}):".format(optimal_size[0]),
            "--add-entry=Override Height ({}):".format(optimal_size[1]),
            "--add-list=Resolutions Found:", "--column-values=Width|Height", "--show-header",
            "--list-values={}".format("|".join("|".join(str(x) for x in s) for s in set(sizes)))]
    try:
        out = subprocess.check_output(QUERY_COMMAND + ['--title=Combine {} files at size {} and fps {} to'.format(len(sizes), optimal_size, optimal_fps)], universal_newlines=True)
        # output from zenity --forms is speparated by a "|" character
        out_file_name, w, h, *_ = out.split("|")
        out_file_name = out_file_name.strip()
        if not out_file_name:
            out_file_name = "unnamed_encoded_{}.mkv".format(random.randint(0,100000))
        try:
            optimal_size[0] = int(w)
        except ValueError:
            pass
        try:
            optimal_size[1] = int(h)
        except ValueError:
            pass
    except subprocess.CalledProcessError:
        print("User Cancelled")
        sys.exit(1)

    # set up a working director
    TMP_DIR = "/dev/shm/vidcompress{:06}".format(random.randint(0,100000))
    subprocess.check_output(["mkdir", "-p", TMP_DIR])

    try:
        # transcode all the video files into mp4

        # scale a video to fit in the frame and letterbox it if it doesn't have the same aspect ratio
        VF_COMMAND = ("scale=(iw*sar)*min({w}/(iw*sar)\\,{h}/ih):ih*min({w}/(iw*sar)\\,{h}/ih)," +
                     "pad={w}:{h}:({w}-iw*min({w}/iw\\,{h}/ih))/2:({h}-ih*min({w}/iw\\,{h}/ih))/2").format(w=optimal_size[0], h=optimal_size[1])
        #TRANSCODE_COMMAND = "ffmpeg -vcodec libx264 -crf 20 -vf scale={}:{} -ac 2 -c:a aac -strict -2 -b:a 128k -ar 44100 -r {}".format(optimal_size[0], optimal_size[1], optimal_fps).split()
        TRANSCODE_COMMAND = "ffmpeg -vcodec libx264 -crf 20 -vf".split() + [VF_COMMAND] + "-ac 2 -c:a aac -strict -2 -b:a 128k -ar 44100 -r {}".format(optimal_fps).split()
        for i,f in enumerate(processing_info):
            full_command = TRANSCODE_COMMAND[:1] + ['-i', f['filename']] + TRANSCODE_COMMAND[1:] + [TMP_DIR + "/transcoded{:04}.mp4".format(i)]
            print("  ".join(full_command))
            subprocess.check_output(full_command)

        # join the files together
        COMBINE_COMMAND = "ffmpeg -f concat -safe 0 -i {}/files.txt -c copy -r {}".format(TMP_DIR, optimal_fps).split()
        with open(TMP_DIR + "/files.txt", 'w+') as file_handle:
            for i,f in enumerate(processing_info):
                file_handle.write("file '{}/transcoded{:04}.mp4'\n".format(TMP_DIR, i))
        full_command = COMBINE_COMMAND + [TMP_DIR + "/outfile.mkv"]
        print("  ".join(full_command))
        subprocess.check_output(full_command)

        # move the file to the appropriate location
        ## this doesn't do what I want
        #if NAUTILUS_SCRIPT_CURRENT_URI == "":
        #    NAUTILUS_SCRIPT_CURRENT_URI = "."
        #out_file = urllib.parse.urlparse(NAUTILUS_SCRIPT_CURRENT_URI + "/{}".format(out_file_name)).path
        #out_file = urllib.parse.unquote(out_file)
        out_file = subprocess.check_output(['dirname', video_files[0]], universal_newlines=True).strip()
        out_file = out_file + "/{}".format(out_file_name)
        full_command = ['mv', TMP_DIR + "/outfile.mkv", out_file]
        print("  ".join(full_command))
        subprocess.check_output(full_command)

    finally:
        full_command = ['rm', '-rf', TMP_DIR]
        print("  ".join(full_command), "\n***Video Processed***\n")
        subprocess.check_output(full_command)
        subprocess.check_output(["zenity", "--notification", "--text=Finished encoding '{}'".format(out_file_name)], universal_newlines=True)



    #print(processing_info)

