import os
import sys
import shutil
import re
import glob
import socket
import time
import functools
import requests
import yt_dlp
from pathlib import Path
import logging
from . import config

def get_default_output_dir():
    """Returns the path to the download folder depending on the OS."""
    # Check for Termux (Android)
    if os.path.exists(config.TERMUX_PREFIX_PATH):
        if os.path.exists("/sdcard/Download"):
            return "/sdcard/Download"
        return "/storage/emulated/0/Download"
    
    # Windows / Linux / MacOS
    return str(Path.home() / "Downloads")

def clean_name(name):
    if not name: return "Video_Dubbed"
    clean = "".join([c if c.isalnum() or c in " .-_()," else "" for c in name])
    return clean.strip()[:60]

def check_write_permissions(path):
    # If folder doesn't exist, try to create it
    if not os.path.exists(path):
        try:
            os.makedirs(path)
        except OSError as e:
            print(f"{config.COLOR_RED}❌ Не удалось создать папку {path}: {e}{config.COLOR_RESET}")
            sys.exit(1)
    
    if not os.access(path, os.W_OK):
        print(f"{config.COLOR_RED}❌ Нет прав на запись в {path}.{config.COLOR_RESET}")
        sys.exit(1)


def get_binary_path(tool_name):
    path = shutil.which(tool_name)
    if path: return path
    termux_path = os.path.join(config.TERMUX_BIN_PATH, tool_name)
    if os.path.exists(termux_path): return termux_path
    return None

def cleanup(error=False):
    # If error occurred, do not delete files for debugging
    if error:
        #print(f"{config.COLOR_YELLOW}⚠️ Временные файлы оставлены для проверки: {config.TEMP_VIDEO_FILENAME}, {config.TEMP_AUDIO_FILENAME}{config.COLOR_RESET}")
        return
    
    # Delete all temporary video and audio files
    files_to_remove = glob.glob("temp_video*") + glob.glob("temp_audio*")
    for f in files_to_remove:
        try:
            os.remove(f)
        except OSError as e:
            logging.debug(f"Could not remove temporary file {f}: {e}")



def retry_on_network_error(func):
    """Decorator for retrying function execution on network errors."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        while True:
            try:
                return func(*args, **kwargs)
            except (OSError, requests.exceptions.RequestException, yt_dlp.utils.DownloadError) as e:
                error_msg = getattr(e, 'msg', str(e))
                # Import cli here to avoid circular dependency
                from . import cli
                if not cli.ask_to_retry(f"Сетевая ошибка в '{func.__name__}': {error_msg}"):
                    print(f"{config.COLOR_RED}Завершение работы по требованию пользователя.{config.COLOR_RESET}")
                    cleanup(True)
                    sys.exit(1)
    return wrapper



@retry_on_network_error
def check_internet():
    """Checks internet connection availability."""
    # Decorator will handle OSError exception
    socket.create_connection(("8.8.8.8", 53), timeout=5)

def validate_url(url):
    if not re.search(r'(youtube\.com|youtu\.?be)', url):
        print(f"{config.COLOR_RED}❌ Ссылка не похожа на YouTube.{config.COLOR_RESET}")
        sys.exit(1)

def install_check():
    required = ['ffmpeg']
    for tool in required:
        if get_binary_path(tool) is None:
            print(f"{config.COLOR_RED}❌ Не найден: {tool}{config.COLOR_RESET}")
            sys.exit(1)

def clean_video_partials():
    """Deletes all temporary video files (but keeps translation audio)."""
    # Delete temp_video.* (mp4, mkv, .part, etc.)
    for f in glob.glob("temp_video*"):
        # Do not touch translation (temp_audio.mp3)
        if "temp_audio" in f: continue
        try:
            os.remove(f)
        except OSError as e:
            logging.debug(f"Could not remove partial file {f}: {e}")

def extract_video_id(url):
    """
    Extracts YouTube video ID from URL.
    """
    from urllib.parse import urlparse, parse_qs
    try:
        parsed_url = urlparse(url)
    except ValueError:
        return None

    if parsed_url.netloc in ["youtu.be"]:
        return parsed_url.path.lstrip("/")
    
    if parsed_url.netloc in ["www.youtube.com", "youtube.com", "m.youtube.com"]:
        if parsed_url.path == "/watch":
            params = parse_qs(parsed_url.query)
            return params.get("v", [None])[0]
        if parsed_url.path.startswith("/embed/"):
            return parsed_url.path.split("/")[2]
        if parsed_url.path.startswith("/v/"):
            return parsed_url.path.split("/")[2]
        if parsed_url.path.startswith("/shorts/"):
            return parsed_url.path.split("/")[2]
            
    return None

