import os
import sys
import requests
import yt_dlp
import shutil
from tqdm import tqdm
from . import config
from . import utils
from . import errors
from . import platform
from . import logger

# Инициализация логгера для модуля downloader
log = logger.get_logger(__name__)

class Logger:
    def debug(self, msg): pass
    def warning(self, msg): pass
    def error(self, msg): print(f"{config.COLOR_RED}{msg}{config.COLOR_RESET}")

def process_audio_only(url, args, skip_translation, translation_success, uploader, title, file_exists_callback=None):
    """Handles the 'audio only' workflow."""
    log.info(f"Processing audio-only mode: skip_translation={skip_translation}, translation_success={translation_success}")

    if skip_translation:
         print(f"\n{config.COLOR_YELLOW}[1/1] Загрузка оригинального аудио...{config.COLOR_RESET}")
         name = f"{utils.clean_name(uploader)} - {utils.clean_name(title)} [Original].mp3"
         final_path = os.path.join(args.output, name)
         if file_exists_callback:
             final_path = file_exists_callback(final_path)
         
         if download_youtube_audio(url, final_path):
             log.info(f"Audio-only download completed: {final_path}")
             print(f"\n{config.COLOR_GREEN}✅ Готово!{config.COLOR_RESET}")
             print(f"📂 {final_path}")
         else:
             log.error("Failed to download YouTube audio")
             print(f"{config.COLOR_RED}❌ Не удалось скачать аудио.{config.COLOR_RESET}")

    elif translation_success:
        print(f"\n{config.COLOR_YELLOW}[2/2] Сохранение аудио...{config.COLOR_RESET}")
        name = f"{utils.clean_name(uploader)} - {utils.clean_name(title)} [AudioTranslation].mp3"
        final_path = os.path.join(args.output, name)
        if file_exists_callback:
             final_path = file_exists_callback(final_path)

        try:
            shutil.copy(config.TEMP_AUDIO_FILENAME, final_path)
            log.info(f"Translation audio saved: {final_path}")
            print(f"\n{config.COLOR_GREEN}✅ Готово!{config.COLOR_RESET}")
            print(f"📂 {final_path}")
        except Exception as e:
            log.error(f"Failed to save translation audio: {e}", exc_info=True)
            print(f"{config.COLOR_RED}❌ Не удалось сохранить аудио: {e}{config.COLOR_RESET}")
    else:
        log.warning("Translation not found, audio-only download cancelled")
        print(f"{config.COLOR_RED}❌ Перевод не найден. Скачивание аудио отменено.{config.COLOR_RESET}")
    
    utils.cleanup()
    return

@utils.retry_on_network_error(retry_callback=None)
def get_available_qualities(url, retry_callback=None):
    """Gets available video resolutions, title and author."""
    log.debug(f"Fetching video info for URL: {url}")
    print(f"{config.COLOR_YELLOW}Анализ...{config.COLOR_RESET}")
    opts = {'quiet': True, 'no_warnings': True, 'logger': Logger()}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
        formats = info.get('formats', [])
        heights = set()
        for f in formats:
            h = f.get('height')
            if h and h > 144:
                # Filter storyboards and non-video formats
                vcodec = f.get('vcodec')
                if vcodec == 'none': continue
                if 'storyboard' in (f.get('format_note') or ''): continue

                heights.add(h)
        log.debug(f"Available qualities: {sorted(list(heights), reverse=True)}")
        return sorted(list(heights), reverse=True), info.get('title', 'Video'), info.get('uploader', 'Unknown'), info.get('duration', 0), info.get('language')

def download_video(url, path, quality_height=None, retry_callback=None, work_dir=None):
    """Downloads video from YouTube using yt-dlp with retry logic."""
    log.info(f"Starting video download: url={url}, quality={quality_height}, path={path}")
    # Define threshold for High-Res (anything above 1080p is considered High-Res)
    is_high_res = quality_height and quality_height > 1080
    
    if is_high_res:
        # For 4K/2K use MKV (VP9 + AAC)
        # Remove ext=mp4 restriction for video
        fmt_str = f'bestvideo[height={quality_height}]+bestaudio[ext=m4a]/best[height={quality_height}]/best'
        ext = 'mkv'
        # Explicitly change path extension so yt-dlp doesn't create temp_video.mp4.mkv
        path = os.path.splitext(path)[0] + '.mkv'
    elif quality_height:
        # For 1080p and below try to take MP4 (H.264) for compatibility.
        # Format 397 (AV1) in MP4 can cause post-processing errors on old ffmpeg.
        # Therefore explicitly prioritize avc (h264).
        fmt_str = (
            f'bestvideo[height={quality_height}][ext=mp4][vcodec^=avc]+bestaudio[ext=m4a]/'  # Best H.264
            f'bestvideo[height={quality_height}][ext=mp4]+bestaudio[ext=m4a]/'                # Any MP4 (incl AV1)
            f'best[height={quality_height}][ext=mp4]/'                                        # Single MP4
            f'bestvideo[height={quality_height}]+bestaudio/'                                  # Fallback: any container
            f'best[height={quality_height}]'                                                  # Fallback: single file
        )
        ext = 'mp4'
    else:
        # By default also try avc if it is mp4
        fmt_str = 'bestvideo[ext=mp4][vcodec^=avc]+bestaudio[ext=m4a]/bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'
        ext = 'mp4'

    pbar = None
    
    while True:
        try:
            pbar = tqdm(total=0, unit='B', unit_scale=True, unit_divisor=1024, 
                        desc=f"[{quality_height if quality_height else 'Best'}p]", 
                        dynamic_ncols=True, colour='blue', bar_format=config.PROGRESS_BAR_FORMAT)

            def hook(d):
                if d['status'] == 'downloading':
                    try:
                        total = d.get('total_bytes') or d.get('total_bytes_estimate')
                        if total: pbar.total = int(total)
                        pbar.n = int(d.get('downloaded_bytes', 0))
                        pbar.refresh()
                    except Exception: pass
                elif d['status'] == 'finished':
                    # Simply update to 100%, closing will be in main function
                    if pbar.total and pbar.n < pbar.total:
                        pbar.n = pbar.total
                        pbar.refresh()

            opts = {
                'format': fmt_str,
                'outtmpl': path,
                'quiet': True,
                'no_warnings': True,
                'logger': Logger(),
                'progress_hooks': [hook],
                'merge_output_format': ext,
                # Important: nopart=True prevents creation of .part files.
                # This is critical for Windows, as renaming .part file can cause access error (WinError 32),
                # if file is still held by antivirus or system.
                'nopart': True,
                'ffmpeg_location': utils.get_binary_path('ffmpeg') or 'ffmpeg',
                'retries': config.RETRY_ATTEMPTS,
                'fragment_retries': config.RETRY_FRAGMENTS,
                'retry_sleep': config.RETRY_SLEEP_SECONDS,
            }
            
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                if pbar and not pbar.disable:
                    pbar.close()
                log.info(f"Video download completed: title={info.get('title')}, height={info.get('height')}, path={path}")
                return info.get('duration', 0), info.get('height', 0), path

        except (OSError, requests.exceptions.RequestException, yt_dlp.utils.DownloadError, ValueError) as e:
            if pbar and not pbar.disable:
                pbar.close()

            # If file downloaded but yt-dlp crashed during post-processing (e.g. response parsing)
            min_size = config.MIN_VALID_VIDEO_SIZE_TERMUX if platform.IS_TERMUX else config.MIN_VALID_VIDEO_SIZE
            if os.path.exists(path):
                size = os.path.getsize(path)
                if size > min_size:
                    # File exists and has reasonable size
                    log.warning(f"Video file exists after error (post-processing crash): {size} bytes, treating as success")
                    return 0, (quality_height if quality_height else 0), path
                else:
                    # File too small, likely corrupted
                    try:
                        os.remove(path)
                    except OSError:
                        pass
                    log.error(f"Downloaded file too small ({size} bytes), likely corrupted")
                    raise errors.YtrdDownloadError(f"Скачанный файл слишком мал ({size} байт), возможно ошибка")

            error_msg = getattr(e, 'msg', str(e))
            log.warning(f"Network error during video download: {error_msg}")

            # If error 416 (Range Not Satisfiable) or codec problems, continuation is impossible.
            # Need to delete partially downloaded/corrupted files before retry.
            is_critical = "416" in error_msg or "codec parameters" in error_msg

            if is_critical:
                log.error(f"Critical download error: {error_msg}")

            # Use callback if provided, otherwise raise exception
            if not retry_callback:
                raise errors.YtrdDownloadError(f"Сетевая ошибка: {error_msg}")

            if is_critical or not retry_callback(f"Сетевая ошибка при скачивании видео: {error_msg}"):
                if is_critical:
                    # If critical error for file, ask user to RESTART from scratch
                    if retry_callback(f"Критическая ошибка файла ({error_msg}).\n{config.COLOR_YELLOW}Очистить временные файлы и скачать заново?"):
                        print(f"{config.COLOR_YELLOW}Очистка временных файлов видео...{config.COLOR_RESET}")
                        utils.clean_video_partials(work_dir)
                        continue

                raise errors.YtrdUserCancelled("Завершение работы по требованию пользователя")

def download_audio(url, path, retry_callback=None):
    """Downloads translation audio track with retry logic."""
    log.debug(f"Downloading translation audio from: {url} to {path}")
    pbar = None
    while True:
        try:
            r = requests.get(url, stream=True, timeout=15)
            r.raise_for_status()
            size = int(r.headers.get('content-length', 0))
            
            pbar = tqdm(total=size, unit='iB', unit_scale=True, desc="Загрузка", 
                      dynamic_ncols=True, colour='green', bar_format=config.PROGRESS_BAR_FORMAT)
            
            with open(path, 'wb') as f:
                for chunk in r.iter_content(1024):
                    pbar.update(len(chunk))
                    f.write(chunk)

            pbar.close()
            log.info(f"Translation audio download completed: {path}")
            return # Successful completion

        except (OSError, requests.exceptions.RequestException) as e:
            if pbar and not pbar.disable:
                pbar.close()

            error_msg = str(e)
            log.warning(f"Network error during audio download: {error_msg}")
            if not retry_callback or not retry_callback(f"Сетевая ошибка при скачивании аудио: {error_msg}"):
                raise errors.YtrdUserCancelled("Завершение работы по требованию пользователя")

def download_youtube_audio(url, path):
    """Downloads audio from YouTube in MP3 format."""
    log.debug(f"Downloading YouTube audio: url={url}, path={path}")
    # Remove extension from path for outtmpl as converter will add .mp3
    base_path = os.path.splitext(path)[0]
    
    opts = {
        'format': 'bestaudio/best',
        'outtmpl': base_path + '.%(ext)s',
        'quiet': True,
        'no_warnings': True,
        'logger': Logger(),
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
        'ffmpeg_location': utils.get_binary_path('ffmpeg') or 'ffmpeg',
        'retries': config.RETRY_ATTEMPTS,
        'fragment_retries': config.RETRY_FRAGMENTS,
        'retry_sleep': config.RETRY_SLEEP_SECONDS,
    }

    # Progress bar (simplified as there is no merge here)
    pbar = tqdm(total=0, unit='B', unit_scale=True, unit_divisor=1024, 
                desc="[Audio]", dynamic_ncols=True, colour='green', bar_format=config.PROGRESS_BAR_FORMAT)
    
    def hook(d):
        if d['status'] == 'downloading':
            try:
                total = d.get('total_bytes') or d.get('total_bytes_estimate')
                if total: pbar.total = int(total)
                pbar.n = int(d.get('downloaded_bytes', 0))
                pbar.refresh()
            except Exception: pass
        elif d['status'] == 'finished':
            if pbar.total: pbar.n = pbar.total
            pbar.refresh()

    opts['progress_hooks'] = [hook]

    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            ydl.download([url])
            pbar.close()
            log.info(f"YouTube audio download completed: {path}")
            return True
    except Exception as e:
        pbar.close()
        log.error(f"YouTube audio download failed: {e}", exc_info=True)
        print(f"{config.COLOR_RED}❌ Ошибка скачивания аудио: {e}{config.COLOR_RESET}")
        return False

def download_subtitles(url, base_path, cookies_path=None):
    """
    Downloads subtitles separately. Tries Russian first, then English as fallback.
    Returns tuple (path, language) if successful, else (None, None).

    Args:
        url: YouTube video URL
        base_path: Base path for subtitle file (without extension)
        cookies_path: Optional path to cookies file (Netscape format)
    """
    log.debug(f"Downloading subtitles: url={url}, base_path={base_path}, cookies={cookies_path}")
    # Auto-detect persistent cookies if not explicitly provided
    if not cookies_path and os.path.exists(config.COOKIES_FILE_PATH):
        cookies_path = config.COOKIES_FILE_PATH
        log.info("Using persistent cookies for subtitles")
        print(f"{config.COLOR_CYAN}🔐 Используются сохраненные cookies{config.COLOR_RESET}")
    
    if cookies_path:
        print(f"{config.COLOR_YELLOW}Скачивание субтитров с cookies...{config.COLOR_RESET}")
    else:
        print(f"{config.COLOR_YELLOW}Скачивание субтитров...{config.COLOR_RESET}")
    
    # We want to name subs same as video base path
    # yt-dlp will add .ru.vtt or .en.vtt etc.
    # We use skip_download=True so we ONLY get subs.
    
    # Try Russian first, then English
    languages_to_try = [
        ('ru', 'rus', 'Русский'),
        ('en', 'eng', 'English')
    ]
    
    for lang_code, lang_meta, lang_name in languages_to_try:
        try:
            opts = {
                'skip_download': True,
                'writesubtitles': True,
                'subtitleslangs': [lang_code],
                'writeautomaticsub': True,
                'outtmpl': base_path, # will append .vtt / .srt
                'quiet': True,
                'no_warnings': True,
                'logger': Logger(),
                'retries': 2,
                'retry_sleep': 3,
            }
            
            # Add cookies if provided
            if cookies_path:
                opts['cookiefile'] = cookies_path
            
            with yt_dlp.YoutubeDL(opts) as ydl:
                ydl.download([url])
                
            # Check what was created
            # Expected: base_path + .ru.vtt/srt or .en.vtt/srt
            candidates = [f"{base_path}.{lang_code}.vtt", f"{base_path}.{lang_code}.srt"]
            for c in candidates:
                if os.path.exists(c):
                    if lang_code != 'ru':
                        log.info(f"Using {lang_name} subtitles as fallback (Russian not found)")
                        print(f"{config.COLOR_CYAN}ℹ️ Русские субтитры не найдены, используются {lang_name}.{config.COLOR_RESET}")
                    else:
                        log.info(f"Subtitles downloaded successfully: {c}")
                    return c, lang_meta  # Return path and language code for metadata
            
        except Exception as e:
            error_str = str(e)

            # Check if it's a rate limiting error (429) or forbidden (403)
            is_rate_limit = "429" in error_str or "Too Many Requests" in error_str
            is_forbidden = "403" in error_str or "Forbidden" in error_str

            if is_rate_limit or is_forbidden:
                log.warning(f"Rate limit or forbidden error for subtitles: {error_str}")
                # Only show error on first attempt (Russian)
                if lang_code == 'ru':
                    print(f"{config.COLOR_YELLOW}⚠️ Превышен лимит запросов YouTube (HTTP 429). Попробуйте позже.{config.COLOR_RESET}")
                return None, None
            # For other errors, try next language
            log.debug(f"Subtitles download failed for {lang_code}: {error_str}")
            continue

    # If no subtitles found in any language
    log.warning("Subtitles not found in any language")
    print(f"{config.COLOR_YELLOW}⚠️ Ошибка при скачивании субтитров: субтитры не найдены{config.COLOR_RESET}")
    return None, None

