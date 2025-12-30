import os
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
VOT_HMAC_KEY = b"bt8xH3VOlb4mqf0nqAibnDOoiPlXsisf"
HTTP_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 YaBrowser/24.4.0.0 Safari/537.36"

# --- Retry Parameters ---
RETRY_ATTEMPTS = 10
RETRY_FRAGMENTS = 10
RETRY_SLEEP_SECONDS = 5
