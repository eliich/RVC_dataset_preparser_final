import tkinter as tk
from tkinter import filedialog, ttk
import os
import re
import atexit
from moviepy.editor import VideoFileClip, AudioFileClip, concatenate_audioclips
import tempfile
import shutil
import pygame
import time

def clear_temp_directory(retry_attempts=3, delay_between_attempts=1):
    temp_dir = os.path.join(tempfile.gettempdir(), "RVC_dataset_preparser")
    for attempt in range(retry_attempts):
        try:
            if os.path.exists(temp_dir):
                shutil.rmtree(temp_dir)
            os.makedirs(temp_dir, exist_ok=True)
            break  # Exit the loop if the directory is successfully cleared
        except PermissionError as e:
            print(f"Attempt {attempt + 1} failed with error: {e}")
            if attempt < retry_attempts - 1:
                time.sleep(delay_between_attempts)  # Wait before retrying
            else:
                print("Failed to clear temporary directory after multiple attempts.")

class SubtitleProcessor:
    def __init__(self, folder_path, progress_bar, progress_label):
        self.folder_path = folder_path
        self.video_subtitles = []
        self.progress_bar = progress_bar
        self.progress_label = progress_label
        self.total_segments = self.calculate_total_segments()
        self.processed_segments = 0
        clear_temp_directory()  # Ensure temp directory is clear before starting

    def run(self):
        self.process_folder()
        return self.video_subtitles

    def calculate_total_segments(self):
        total_segments = 0
        for file in os.listdir(self.folder_path):
            if file.endswith(".srt"):
                srt_path = os.path.join(self.folder_path, file)
                times = self.parse_srt_file(srt_path)
                total_segments += len(times)
        return total_segments

    def process_folder(self):
        for file in os.listdir(self.folder_path):
            if file.endswith(".srt"):
                self.process_srt_file(file)

    def process_srt_file(self, file_name):
        srt_path = os.path.join(self.folder_path, file_name)
        base_name = os.path.splitext(file_name)[0]
        times = self.parse_srt_file(srt_path)
        for media_ext in ['.mp4', '.mkv', '.avi', '.mp3', '.wav']:
            media_path = os.path.join(self.folder_path, base_name + media_ext)
            if os.path.exists(media_path):
                self.process_media_file(media_path, times)
                break

    def process_media_file(self, media_path, times):
        file_ext = os.path.splitext(media_path)[1].lower()
        is_audio = file_ext in ['.mp3', '.wav']
        if is_audio:
            clip = AudioFileClip(media_path)
        else:
            clip = VideoFileClip(media_path)

        clip_duration = clip.duration

        for start, end in times:
            start_sec = SubtitleProcessor.timecode_to_seconds(start)
            end_sec = SubtitleProcessor.timecode_to_seconds(end)
            end_sec = min(end_sec, clip_duration)

            adjusted_end = SubtitleProcessor.seconds_to_timecode(end_sec)

            audio_segment_path = self.segment_audio(start, adjusted_end, media_path, is_audio=is_audio)
            self.video_subtitles.append({
                "start_time": start,
                "end_time": adjusted_end,
                "media_path": media_path,
                "audio_segment_path": audio_segment_path
            })

    def segment_audio(self, start, end, media_path, is_audio):
        start_sec = SubtitleProcessor.timecode_to_seconds(start)
        end_sec = SubtitleProcessor.timecode_to_seconds(end)
        if is_audio:
            clip = AudioFileClip(media_path)
        else:
            clip = VideoFileClip(media_path).audio
        end_sec = min(end_sec, clip.duration)
        subclip = clip.subclip(start_sec, end_sec)
        temp_dir = os.path.join(tempfile.gettempdir(), "RVC_dataset_preparser")
        os.makedirs(temp_dir, exist_ok=True)
        unique_file_name = f"{os.path.basename(media_path).split('.')[0]}_{start.replace(':', '-').replace(',', '-')}_to_{end.replace(':', '-').replace(',', '-')}.wav"
        temp_audio_path = os.path.join(temp_dir, unique_file_name)
        subclip.write_audiofile(temp_audio_path, codec='pcm_s16le')
        self.processed_segments += 1
        self.update_progress()
        return temp_audio_path

    def update_progress(self):
        progress_fraction = self.processed_segments / self.total_segments
        self.progress_bar['value'] = progress_fraction * 100
        self.progress_label.config(text=f"Processing segment {self.processed_segments} of {self.total_segments}")
        root.update_idletasks()

    @staticmethod
    def parse_srt_file(srt_path):
        pattern = re.compile(r'\d+\s+(\d{2}:\d{2}:\d{2},\d{3}) --> (\d{2}:\d{2}:\d{2},\d{3})')
        with open(srt_path, 'r', encoding='utf-8') as file:
            content = file.read()
        times = pattern.findall(content)
        return [(start, end) for start, end in times]

    @staticmethod
    def timecode_to_seconds(timecode):
        hours, minutes, seconds_milliseconds = timecode.split(':')
        seconds, milliseconds = seconds_milliseconds.split(',')
        hours = int(hours)
        minutes = int(minutes)
        seconds = int(seconds)
        milliseconds = int(milliseconds)
        return 3600 * hours + 60 * minutes + seconds + milliseconds / 1000.0

    @staticmethod
    def seconds_to_timecode(seconds):
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        seconds_remainder = seconds % 60
        milliseconds = int((seconds_remainder - int(seconds_remainder)) * 1000)
        seconds_final = int(seconds_remainder)
        return f"{hours:02}:{minutes:02}:{seconds_final:02},{milliseconds:03}"

def concatenate_and_save_segments(saved_segments):
    time_ranges_by_path = {}
    audio_clips = []

    for segment in saved_segments:
        media_path = segment['media_path']
        start_time = SubtitleProcessor.timecode_to_seconds(segment['start_time'])
        end_time = SubtitleProcessor.timecode_to_seconds(segment['end_time'])

        if media_path not in time_ranges_by_path:
            time_ranges_by_path[media_path] = [start_time, end_time]
        else:
            time_ranges_by_path[media_path][0] = min(time_ranges_by_path[media_path][0], start_time)
            time_ranges_by_path[media_path][1] = max(time_ranges_by_path[media_path][1], end_time)

    for media_path, (start_time, end_time) in time_ranges_by_path.items():
        file_ext = os.path.splitext(media_path)[1].lower()
        is_audio = file_ext in ['.mp3', '.wav']

        if is_audio:
            clip = AudioFileClip(media_path)
        else:
            clip = VideoFileClip(media_path).audio

        continuous_clip = clip.subclip(start_time, end_time)
        audio_clips.append(continuous_clip)

    if audio_clips:
        final_clip = concatenate_audioclips(audio_clips)
        output_path = os.path.join(os.path.dirname(media_path), "finalResults.wav")
        final_clip.write_audiofile(output_path, codec='pcm_s16le')
        print(f"Saved final audio to: {output_path}")

    # Clear temporary directory after concatenation
    clear_temp_directory()

global root

def select_folder():
    folder_path = filedialog.askdirectory()
    if folder_path:
        progress_label = tk.Label(root, text="Processing...", anchor='w')
        progress_label.pack(fill=tk.X, padx=10, pady=5)
        progress = ttk.Progressbar(root, orient=tk.HORIZONTAL, length=100, mode='determinate')
        progress.pack(fill=tk.X, padx=10, pady=5)
        processor = SubtitleProcessor(folder_path, progress, progress_label)
        video_subtitles = processor.run()
        if video_subtitles:
            pygame.mixer.init()
            play_audio_segment(video_subtitles[0]['audio_segment_path'])
            setup_gui_for_audio_control(video_subtitles)
        else:
            print("No audio segments were processed.")
        progress_label.pack_forget()
        progress.pack_forget()
    else:
        print("No folder was selected.")

def play_audio_segment(path):
    pygame.mixer.music.load(path)
    pygame.mixer.music.play(-1)

def stop_audio():
    pygame.mixer.music.stop()

def setup_gui_for_audio_control(video_subtitles):
    for widget in root.winfo_children():
        widget.destroy()

    current_index = [0]
    saved_segments = []
    action_history = []

    position_label = tk.Label(root, text=f"Current Position: {current_index[0]+1}/{len(video_subtitles)}", anchor='w')
    position_label.pack(fill=tk.X, padx=10, pady=5)

    def update_current_position_label():
        position_label.config(text=f"Current Position: {current_index[0]+1}/{len(video_subtitles)}")

    def log_saved_segments():
        # Future placeholder for enhanced logging or actions
        pass

    def skip():
        stop_audio()  # Stop the currently playing audio
        if current_index[0] + 1 < len(video_subtitles):
            action_history.append(('skip', current_index[0]))
            current_index[0] += 1
            play_audio_segment(video_subtitles[current_index[0]]['audio_segment_path'])
            update_current_position_label()
        else:
            concatenate_and_save_segments(saved_segments)

    def add_and_skip():
        stop_audio()  # Stop the currently playing audio
        if current_index[0] < len(video_subtitles):
            saved_segments.append(video_subtitles[current_index[0]])
            action_history.append(('add_and_skip', current_index[0]))
            current_index[0] += 1
            if current_index[0] < len(video_subtitles):
                play_audio_segment(video_subtitles[current_index[0]]['audio_segment_path'])
            update_current_position_label()
        if current_index[0] >= len(video_subtitles):
            concatenate_and_save_segments(saved_segments)

    def redo_last_choice():
        if action_history:
            last_action, index = action_history.pop()
            if last_action == 'skip':
                current_index[0] = index
            elif last_action == 'add_and_skip':
                if saved_segments and video_subtitles[index] in saved_segments:
                    saved_segments.remove(video_subtitles[index])
                current_index[0] = index
            play_audio_segment(video_subtitles[current_index[0]]['audio_segment_path'])
            update_current_position_label()

    def pause_resume():
        if pygame.mixer.music.get_busy():
            pygame.mixer.music.pause()
        else:
            pygame.mixer.music.unpause()

    def restart():
        select_folder()

    skip_button = tk.Button(root, text="Skip", command=skip)
    skip_button.pack(fill=tk.X, padx=10, pady=5)

    add_and_skip_button = tk.Button(root, text="Add & Skip", command=add_and_skip)
    add_and_skip_button.pack(fill=tk.X, padx=10, pady=5)

    redo_button = tk.Button(root, text="Redo Last Choice", command=redo_last_choice)
    redo_button.pack(fill=tk.X, padx=10, pady=5)

    pause_resume_button = tk.Button(root, text="Pause/Resume", command=pause_resume)
    pause_resume_button.pack(fill=tk.X, padx=10, pady=5)

    restart_button = tk.Button(root, text="Select Folder", command=restart)
    restart_button.pack(fill=tk.X, padx=10, pady=20)

    update_current_position_label()

def main():
    global root
    root = tk.Tk()
    root.title("Subtitle Processor")
    root.geometry('300x275')
    select_folder_button = tk.Button(root, text="Select Folder", command=select_folder)
    select_folder_button.pack(fill=tk.X, padx=10, pady=20)

    # Register the cleanup function to clear the temporary directory on app exit
    atexit.register(clear_temp_directory)

    root.mainloop()

if __name__ == "__main__":
    main()
