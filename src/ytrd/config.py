import os
import warnings
from pathlib import Path
from . import platform

# --- Termux Settings (импортированы из platform.py для обратной совместимости) ---
TERMUX_PREFIX_PATH = platform.TERMUX_PREFIX_PATH
TERMUX_BIN_PATH = platform.TERMUX_BIN_PATH


TEMP_VIDEO_FILENAME = "temp_video.mp4"
TEMP_AUDIO_FILENAME = "temp_audio.mp3"

# --- Cookies ---
# Save cookies in user's home directory for persistence
COOKIES_FILE_PATH = os.path.join(Path.home(), '.ytrd_cookies.txt')
HISTORY_FILE_PATH = os.path.join(Path.home(), '.ytrd_history.json')

# --- Colors ---
COLOR_CYAN = "\033[96m"
COLOR_GREEN = "\033[92m"
COLOR_YELLOW = "\033[93m"
COLOR_RED = "\033[91m"
COLOR_RESET = "\033[0m"

# --- Progress Bar ---
PROGRESS_BAR_FORMAT = "{l_bar}{bar}| {n_fmt}/{total_fmt} [{rate_fmt}]"
PROGRESS_BAR_TIME_FORMAT = "{l_bar}{bar}| {n_fmt}/{total_fmt}s"

# --- VOT Settings ---
# Попытка загрузить ключ из .env файла
_DEFAULT_HMAC_KEY = 'bt8xH3VOlb4mqf0nqAibnDOoiPlXsisf'
_VOT_HMAC_KEY = os.getenv('VOT_HMAC_KEY', _DEFAULT_HMAC_KEY)

if not os.getenv('VOT_HMAC_KEY'):
    if platform.IS_TERMUX:
        warnings.warn(
            "Используется дефолтный VOT_HMAC_KEY. "
            "Рекомендуется создать ~/ytrd/.env с VOT_HMAC_KEY для получения собственного ключа."
        )
    else:
        warnings.warn(
            "Используется дефолтный VOT_HMAC_KEY. "
            "Рекомендуется установить VOT_HMAC_KEY через переменную окружения или .env файл."
        )

VOT_HMAC_KEY = _VOT_HMAC_KEY.encode() if isinstance(_VOT_HMAC_KEY, str) else _VOT_HMAC_KEY
HTTP_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 YaBrowser/24.4.0.0 Safari/537.36"

# --- Retry Parameters ---
RETRY_ATTEMPTS = 10
RETRY_FRAGMENTS = 10
RETRY_SLEEP_SECONDS = 5

# --- Defaults ---
DEFAULT_VIDEO_DURATION = 341.0  # Средняя длительность видео для fallback
MIN_VALID_VIDEO_SIZE = 1024 * 100  # Минимальный размер валидного видео (100 KB)
MIN_VALID_VIDEO_SIZE_TERMUX = 1024 * 50  # Для Termux (50 KB)
MAX_FILENAME_LENGTH = 60  # Максимальная длина имени файла
