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
from . import config
from . import errors
from . import platform
from . import logger

# Инициализация логгера для модуля utils
log = logger.get_logger(__name__)

def get_default_output_dir():
    """Возвращает путь к папке загрузок (обёртка для обратной совместимости)."""
    return str(platform.get_default_output_dir())

def clean_name(name):
    if not name: return "Video_Dubbed"
    clean = "".join([c if c.isalnum() or c in " .-_()," else "" for c in name])
    return clean.strip()[:60]

def check_write_permissions(path):
    """Проверяет права на запись с учётом особенностей платформы."""
    path_obj = Path(path)

    if not path_obj.exists():
        try:
            path_obj.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            if platform.IS_TERMUX:
                raise errors.YtrdPlatformError(
                    f"Не удалось создать папку {path}. "
                    f"На Android Termux убедитесь, что вы предоставили разрешение на запись: termux-setup-storage"
                ) from e
            raise errors.YtrdFileError(f"Не удалось создать папку {path}: {e}") from e

    if not os.access(path_obj, os.W_OK):
        if platform.IS_TERMUX:
            raise errors.YtrdPlatformError(
                f"Нет прав на запись в {path}. "
                "Выполните: termux-setup-storage"
            )
        raise errors.YtrdFileError(f"Нет прав на запись в {path}")


def get_binary_path(tool_name):
    """Находит бинарный файл (обёртка для обратной совместимости)."""
    path = platform.get_binary_path(tool_name)
    return str(path) if path else None

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
            log.debug(f"Could not remove temporary file {f}: {e}")



def retry_on_network_error(retry_callback=None):
    """Декоратор с callback для повторной попытки.

    Args:
        retry_callback: Callable[[str], bool] - функция, принимающая сообщение
                       и возвращающая True для повтора. Если None, выбрасывает исключение.

    Returns:
        Декоратор функции
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            while True:
                try:
                    return func(*args, **kwargs)
                except (OSError, requests.exceptions.RequestException, yt_dlp.utils.DownloadError) as e:
                    error_msg = getattr(e, 'msg', str(e))
                    if retry_callback is None or not retry_callback(f"Сетевая ошибка в '{func.__name__}': {error_msg}"):
                        raise errors.YtrdNetworkError(f"Сетевая ошибка: {error_msg}") from e
        return wrapper
    return decorator


def check_internet():
    """Checks internet connection availability."""
    # Decorator will handle OSError exception
    socket.create_connection(("8.8.8.8", 53), timeout=5)

def validate_url(url):
    if not re.search(r'(youtube\.com|youtu\.?be)', url):
        raise errors.YtrdValidationError("Ссылка не похожа на YouTube")

def install_check():
    required = ['ffmpeg']
    for tool in required:
        if get_binary_path(tool) is None:
            raise errors.YtrdExternalToolError(f"Не найден: {tool}")

def clean_video_partials():
    """Deletes all temporary video files (but keeps translation audio)."""
    # Delete temp_video.* (mp4, mkv, .part, etc.)
    for f in glob.glob("temp_video*"):
        # Do not touch translation (temp_audio.mp3)
        if "temp_audio" in f: continue
        try:
            os.remove(f)
        except OSError as e:
            log.debug(f"Could not remove partial file {f}: {e}")

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

