import subprocess
import sys
import shlex
import os
import shutil
from tqdm import tqdm
from . import config
from . import utils
from . import cli

def build_ffmpeg_command(mode, final_path, is_mkv=False, sub_path=None, sub_lang='rus'):
    """
    Builds the FFmpeg command list based on the selected mode.
    
    Args:
        mode (int): Mixing mode (1: Dub, 2: Mix, 3: Dual).
        final_path (str): Output file path.
        is_mkv (bool): Whether the output format is MKV.
        sub_path (str, optional): Path to the subtitle file.
        sub_lang (str, optional): Language code for subtitle metadata (e.g., 'rus', 'eng').
        
    Returns:
        list: The complete FFmpeg command as a list of arguments.
    """
    ffmpeg_exec = utils.get_binary_path('ffmpeg') or 'ffmpeg'
    
    # --- Block 1: Base Command & Inputs ---
    base_cmd = [
        ffmpeg_exec, 
        '-y',                                  # Overwrite output files
        '-loglevel', 'quiet',                  # Suppress banner
        '-progress', 'pipe:1',                 # Progress to stdout
        '-threads', '0',                       # Auto threads
        '-i', config.TEMP_VIDEO_FILENAME,      # Input 0: Video
        '-i', config.TEMP_AUDIO_FILENAME       # Input 1: Audio (Translation)
    ]
    
    if sub_path:
        base_cmd.extend(['-i', sub_path])      # Input 2: Subtitles
    
    cmd_settings = []
    
    # --- Block 2: Mode Logic ---
    if mode == 2: # Mode 2: Mixing
        # Filter: reduce original volume (20%), boost dub (120%), mix them.
        filter_complex = "[0:a]volume=0.2[orig];[1:a]volume=1.2[dub];[orig][dub]amix=inputs=2:duration=shortest[out]"
        
        cmd_settings = [
            # Filter
            '-filter_complex', filter_complex,
            
            # Mapping
            '-map', '0:v',        # Video from Input 0
            '-map', '[out]',      # Audio from Filter
            
            # Codecs
            '-c:v', 'copy',       # Copy video stream
            '-c:a', 'aac',        # Re-encode audio to AAC
            '-b:a', '128k',       # Audio bitrate
            '-strict', '-2'
        ]
        
    elif mode == 3: # Mode 3: Dual Audio
        cmd_settings = [
            # Mapping
            '-map', '0:v',        # Video
            '-map', '0:a',        # Audio 1 (Original)
            '-map', '1:a',        # Audio 2 (Translation)
            
            # Codecs - explicit for video and audio only, not global
            '-c:v', 'copy',       # Copy video stream
            '-c:a', 'copy',       # Copy audio streams
            
            # Metadata: Track 1 (Original)
            '-metadata:s:a:0', 'title=Original',
            '-metadata:s:a:0', 'handler_name=Original',
            
            # Metadata: Track 2 (Russian)
            '-metadata:s:a:1', 'title=Русский',
            '-metadata:s:a:1', 'handler_name=Русский',
            '-metadata:s:a:1', 'language=rus',
        ]
        
        if not is_mkv:
            # Fix for AAC in MP4
            cmd_settings.extend(['-bsf:a:0', 'aac_adtstoasc'])
            
    else: # Mode 1: Dub Only (Fallback)
        cmd_settings = [
            # Mapping
            '-map', '0:v',        # Video
            '-map', '1:a',        # Audio (Translation)
            
            # Codecs - explicit for video and audio only
            '-c:v', 'copy',
            '-c:a', 'copy',
        ]

    # --- Block 2.5: Subtitles ---
    if sub_path:
        # Check output container capability
        if not is_mkv:
            # MP4 supports 'mov_text', MKV supports 'srt', 'ass', etc.
            # We assume input is VTT/SRT.
            # For MP4 we must convert to mov_text.
            cmd_settings.extend(['-c:s', 'mov_text'])
        else:
            # For MKV just copy or use srt
            cmd_settings.extend(['-c:s', 'srt']) # Force SRT to be safe or 'copy' if input is already srt/vtt compatible
            
        cmd_settings.extend([
            '-map', '2:s',
            '-metadata:s:s:0', f'language={sub_lang}',
            '-metadata:s:s:0', f'title={"Русский" if sub_lang == "rus" else "English"}'
        ])

    # --- Block 3: Final Output Settings ---
    cmd_final = [
        '-movflags', '+faststart', # Move metadata to beginning for web playback
        final_path
    ]
    
    return base_cmd + cmd_settings + cmd_final

def run_ffmpeg(cmd_list, duration, mode_name="FFmpeg"):
    """
    Executes the FFmpeg command with a progress bar.
    
    Args:
        cmd_list (list): The command to execute.
        duration (float): Video duration in seconds (for progress bar).
        mode_name (str): Label for the progress bar.
    """
    # Replace quiet with error for debugging purposes if needed
    try:
        idx = cmd_list.index('-loglevel')
        if cmd_list[idx + 1] == 'quiet':
            # Note: We keep it 'quiet' in code but logic allows switching. 
            # If we wanted to force error level on debug, we would do it here.
            # Currently just keeping usage consistent with original logic check.
            pass
            # cmd_list[idx + 1] = 'error' 
    except (ValueError, IndexError):
        pass # -loglevel not found

    try:
        # Popen with universal_newlines=True to handle text output
        proc = subprocess.Popen(
            cmd_list,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, 
            universal_newlines=True,
            shell=False,
            bufsize=1, 
            encoding='utf-8',
            errors='replace'
        )
        
        fmt = config.PROGRESS_BAR_TIME_FORMAT
        duration = int(duration) if duration else 100
        pbar = tqdm(
            total=duration,
            unit="s",
            desc=f"[{mode_name}]",
            dynamic_ncols=True,
            colour='yellow',
            bar_format=fmt
        )
        
        last = 0
        full_log = [] # Save all output for debugging usage
        
        # Read stdout line by line (includes merged stderr)
        while True:
            line = proc.stdout.readline()
            if not line:
                if proc.poll() is not None:
                    break
                continue
                
            full_log.append(line)
            line_str = line.strip()
            if not line_str:
                continue

            # Parse time progress from FFmpeg output
            current_sec = None
            if "out_time_us=" in line_str:
                try:
                    us = int(line_str.split('=')[1].strip())
                    current_sec = us // 1000000
                except (ValueError, IndexError):
                    pass
            elif "out_time=" in line_str: # Fallback format
                try:
                    # out_time=00:00:05.123456
                    t_str = line_str.split('=')[1].strip()
                    parts = t_str.split(':')
                    if len(parts) == 3:
                        h, m, s = int(parts[0]), int(parts[1]), float(parts[2])
                        current_sec = int(h * 3600 + m * 60 + s)
                except (ValueError, IndexError):
                    pass

            # Update progress bar
            if current_sec is not None:
                if current_sec > duration:
                    current_sec = duration
                if current_sec > last:
                    pbar.update(current_sec - last)
                    last = current_sec
        
        rc = proc.poll()
        if rc == 0:
            # Force completion on success
            if pbar.total and pbar.n < pbar.total:
                pbar.n = pbar.total
                pbar.refresh()
        
        pbar.close()
        
        if rc != 0:
            print(f"\n{config.COLOR_RED}❌ Ошибка FFmpeg (код {rc}):{config.COLOR_RESET}")
            print(f"{config.COLOR_YELLOW}Команда:{config.COLOR_RESET} {shlex.join(cmd_list)}")
            print(f"{config.COLOR_RED}Лог выполнения:{config.COLOR_RESET}")
            print("".join(full_log[-20:])) # Print last 20 lines of log
            utils.cleanup(error=True)
            sys.exit(1)
            
    except (OSError, FileNotFoundError) as e:
        print(f"\n{config.COLOR_RED}❌ Ошибка запуска FFmpeg: {e}{config.COLOR_RESET}")
        print(f"{config.COLOR_YELLOW}Убедитесь, что ffmpeg установлен и доступен в PATH.{config.COLOR_RESET}")
        sys.exit(1)

def convert_to_srt(sub_path):
    """
    Converts subtitle file to SRT format if necessary.
    Checks for file existence and size.
    Returns path to valid SRT file, or original path if conversion failed but file exists,
    or None if file is invalid/empty.
    """
    if not sub_path or not os.path.exists(sub_path):
        return None
    
    if os.path.getsize(sub_path) == 0:
        print(f"{config.COLOR_YELLOW}⚠️ Файл субтитров пуст, пропускаем.{config.COLOR_RESET}")
        return None

    # If already SRT, just return it
    if sub_path.endswith('.srt'):
        return sub_path

    # Try to convert to SRT
    # We create a new path for SRT
    base_name = os.path.splitext(sub_path)[0]
    srt_path = f"{base_name}.srt"
    
    ffmpeg_exec = utils.get_binary_path('ffmpeg') or 'ffmpeg'
    try:
        # Check if SRT already exists and is valid
        if os.path.exists(srt_path) and os.path.getsize(srt_path) > 0:
            return srt_path
            
        cmd = [ffmpeg_exec, '-y', '-loglevel', 'error', '-i', sub_path, srt_path]
        subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        
        if os.path.exists(srt_path) and os.path.getsize(srt_path) > 0:
            return srt_path
    except Exception as e:
        # Conversion failed, print warning but return original (maybe ffmpeg can handle it)
        # However, for MP4, VTT often fails with mov_text if not converted.
        # But we return original as fallback.
        print(f"{config.COLOR_YELLOW}⚠️ Не удалось конвертировать субтитры в SRT: {e}{config.COLOR_RESET}")
        pass
        
    return sub_path

def process_video_merge(current_path, ext, translation_success, uploader, title, actual_height, args, duration, sub_path=None, sub_lang='rus'):
    """Handles the video merging/processing workflow."""
    
    # Pre-process subtitles: Convert and Validate
    if sub_path:
        sub_path = convert_to_srt(sub_path)
        if not sub_path:
            print(f"{config.COLOR_YELLOW}⚠️ Субтитры были отброшены (пустой файл или ошибка).{config.COLOR_RESET}")

    # Use FFmpeg to merge video and audio.
    # Depending on mode, either copy streams or use amix filter.
    if translation_success:
        print(f"\n{config.COLOR_YELLOW}[3/3] Сборка файла...{config.COLOR_RESET}")
        
        mode = 2 # Default (Mix)
        if args.mix:
            mode = 2
        elif args.dual:
            mode = 3
        else:
            mode = cli.ask_merge_mode()
            
        # Mode short tags
        mode_tags = {1: "Dub", 2: "Mix", 3: "Dual"}
        
        mode_str = f"[{mode_tags.get(mode, 'Dub')}]"
        mode_name = mode_tags.get(mode, 'FFmpeg').upper()
        
        # Resolution
        res_str = f"[{actual_height}p]" if actual_height else ""
        
        # Use the same extension for final file as for video
        name = f"{utils.clean_name(uploader)} - {utils.clean_name(title)} {res_str}{mode_str}.{ext}"
        final_path = os.path.join(args.output, name)
        
        # --- Existence check ---
        final_path = cli.handle_existing_file(final_path)
        
        cmd_list = build_ffmpeg_command(mode, final_path, is_mkv=(ext=='mkv'), sub_path=sub_path, sub_lang=sub_lang)
        
        # Substitute input file in command (config.TEMP_VIDEO_FILENAME -> current_path)
        try:
            # config.TEMP_VIDEO_FILENAME constant "temp_video.mp4". 
            # build_ffmpeg_command adds it to list.
            # Find and replace with real path.
            idx = cmd_list.index(config.TEMP_VIDEO_FILENAME)
            cmd_list[idx] = current_path
        except ValueError:
            pass 
            
        run_ffmpeg(cmd_list, duration, mode_name)
    else:
        # No translation - just process original video
        # If we have subtitles, need to use ffmpeg to embed them
        res_str = f"[{actual_height}p]" if actual_height else ""
        name = f"{utils.clean_name(uploader)} - {utils.clean_name(title)} {res_str}.{ext}"
        final_path = os.path.join(args.output, name)
        
        # --- Existence check ---
        final_path = cli.handle_existing_file(final_path)
        
        if sub_path:
            # Need to use ffmpeg to embed subtitles into video
            print(f"\n{config.COLOR_YELLOW}Встраивание субтитров...{config.COLOR_RESET}")
            
            ffmpeg_exec = utils.get_binary_path('ffmpeg') or 'ffmpeg'
            is_mkv = (ext == 'mkv')
            
            cmd_list = [
                ffmpeg_exec,
                '-y',
                '-loglevel', 'quiet',
                '-progress', 'pipe:1',
                '-i', current_path,      # Input 0: Video
                '-i', sub_path,          # Input 1: Subtitles
                '-map', '0:v',           # Map only VIDEO stream from input 0
                '-map', '0:a',           # Map only AUDIO streams from input 0
                '-map', '1:s',           # Map subtitle stream from input 1
                '-c:v', 'copy',          # Copy video without re-encoding
                '-c:a', 'copy',          # Copy audio without re-encoding
            ]
            
            # Subtitle codec based on container
            if not is_mkv:
                cmd_list.extend(['-c:s', 'mov_text'])
            else:
                cmd_list.extend(['-c:s', 'srt'])
            
            # Subtitle metadata
            subtitle_title = "Русский" if sub_lang == 'rus' else "English"
            cmd_list.extend([
                '-metadata:s:s:0', f'language={sub_lang}',
                '-metadata:s:s:0', f'title={subtitle_title}',
                '-movflags', '+faststart',
                final_path
            ])
            
            run_ffmpeg(cmd_list, duration, "SUBTITLE")
        else:
            # Just copy file without processing
            print(f"Копирование файла в '{final_path}'...")
            try:
                shutil.copy(current_path, final_path)
            except Exception as e:
                print(f"{config.COLOR_RED}❌ Не удалось скопировать файл: {e}{config.COLOR_RESET}")

    # --- Completion ---
    utils.cleanup()
    if os.path.exists(final_path):
        print(f"\n{config.COLOR_GREEN}✅ Готово!{config.COLOR_RESET}")
        print(f"📂 {final_path}")
    else:
        print(f"\n{config.COLOR_YELLOW}Операция отменена. Временные файлы удалены.{config.COLOR_RESET}")
