import os
import subprocess
import sys
import shutil
import re
import requests
import argparse
import json
import yt_dlp
import socket
import shlex
import functools
import time
import glob
from . import vot
from tqdm import tqdm
from pathlib import Path
import platform

# --- НАСТРОЙКИ ---
# --- НАСТРОЙКИ ---
def get_default_output_dir():
    """Возвращает путь к папке загрузок в зависимости от ОС."""
    # Проверка на Termux (Android)
    if os.path.exists("/data/data/com.termux/files/usr"):
        if os.path.exists("/sdcard/Download"):
            return "/sdcard/Download"
        return "/storage/emulated/0/Download"
    
    # Windows / Linux / MacOS
    return str(Path.home() / "Downloads")

OUTPUT_DIR = get_default_output_dir()
TEMP_VIDEO = "temp_video.mp4"
TEMP_AUDIO = "temp_audio.mp3"
TERMUX_PREFIX = "/data/data/com.termux/files/usr"
TERMUX_BIN = os.path.join(TERMUX_PREFIX, "bin")

# Добавляем пути Termux
os.environ["PATH"] = f"{TERMUX_BIN}:{os.environ.get('PATH', '')}"

# Цвета
CYAN = "\033[96m"
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
RESET = "\033[0m"

CLEAN_BAR = "{l_bar}{bar}| {n_fmt}/{total_fmt} [{rate_fmt}]"

def ask_to_retry(error_message):
    """Выводит сообщение об ошибке и спрашивает пользователя о повторной попытке."""
    print(f"\n{RED}❌ {error_message}{RESET}")
    while True:
        try:
            choice = input(f"{YELLOW}Попробовать снова? (y/n): {RESET}").lower().strip()
            if choice in ('y', 'yes', 'д', 'да'):
                return True
            if choice in ('n', 'no', 'н', 'нет'):
                return False
        except (KeyboardInterrupt, EOFError):
            return False

def ask_yes_no(question):
    """Задает вопрос и ждет ответа y/n."""
    while True:
        try:
            choice = input(f"{question} (y/n): ").lower().strip()
            if choice in ('y', 'yes', 'д', 'да'):
                return True
            if choice in ('n', 'no', 'н', 'нет'):
                return False
        except (KeyboardInterrupt, EOFError):
            return False

def retry_on_network_error(func):
    """Декоратор для повторных попыток выполнения функции при сетевых ошибках."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        while True:
            try:
                return func(*args, **kwargs)
            except (OSError, requests.exceptions.RequestException, yt_dlp.utils.DownloadError) as e:
                error_msg = getattr(e, 'msg', str(e))
                if not ask_to_retry(f"Сетевая ошибка в '{func.__name__}': {error_msg}"):
                    print(f"{RED}Завершение работы по требованию пользователя.{RESET}")
                    cleanup(True)
                    sys.exit(1)
    return wrapper

@retry_on_network_error
def check_internet():
    """Проверяет наличие интернет-соединения."""
    # Декоратор обработает исключение OSError
    socket.create_connection(("8.8.8.8", 53), timeout=5)

def check_write_permissions(path):
    # Если папка не существует, пробуем создать
    if not os.path.exists(path):
        try:
            os.makedirs(path)
        except OSError as e:
            print(f"{RED}❌ Не удалось создать папку {path}: {e}{RESET}")
            sys.exit(1)
    
    if not os.access(path, os.W_OK):
        print(f"{RED}❌ Нет прав на запись в {path}.{RESET}")
        sys.exit(1)

def validate_url(url):
    if not re.search(r'(youtube\.com|youtu\.?be)', url):
        print(f"{RED}❌ Ссылка не похожа на YouTube.{RESET}")
        sys.exit(1)

def get_binary_path(tool_name):
    path = shutil.which(tool_name)
    if path: return path
    termux_path = os.path.join(TERMUX_BIN, tool_name)
    if os.path.exists(termux_path): return termux_path
    return None

def install_check():
    required = ['ffmpeg']
    for tool in required:
        if get_binary_path(tool) is None:
            print(f"{RED}❌ Не найден: {tool}{RESET}")
            sys.exit(1)

def cleanup(error=False):
    # Если произошла ошибка, не удаляем файлы для отладки
    if error:
        #print(f"{YELLOW}⚠️ Временные файлы оставлены для проверки: {TEMP_VIDEO}, {TEMP_AUDIO}{RESET}")
        return
    try:
        # Удаляем все временные файлы видео и аудио
        for f in glob.glob("temp_video*"):
            try: os.remove(f)
            except OSError: pass
            
        for f in glob.glob("temp_audio*"):
            try: os.remove(f)
            except OSError: pass
    except Exception: pass

def clean_video_partials():
    """Удаляет все временные файлы видео (но оставляет аудио перевода)."""
    try:
        # Удаляем temp_video.* (mp4, mkv, .part и т.д.)
        for f in glob.glob("temp_video*"):
            # Не трогаем перевод (temp_audio.mp3)
            if "temp_audio" in f: continue
            try:
                os.remove(f)
            except OSError: pass
    except Exception: pass

def clean_name(name):
    if not name: return "Video_Dubbed"
    clean = "".join([c if c.isalnum() or c in " .-_()," else "" for c in name])
    return clean.strip()[:60]

class Logger:
    def debug(self, msg): pass
    def warning(self, msg): pass
    def error(self, msg): print(f"{RED}{msg}{RESET}")

@retry_on_network_error
def get_available_qualities(url):
    """Получает доступные разрешения видео, его название и автора."""
    print(f"{YELLOW}Анализ...{RESET}")
    opts = {'quiet': True, 'no_warnings': True, 'logger': Logger()}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
        formats = info.get('formats', [])
        heights = set()
        for f in formats:
            h = f.get('height')
            if h and h > 144:
                # Фильтруем раскадровки и не-видео форматы
                vcodec = f.get('vcodec')
                if vcodec == 'none': continue 
                if 'storyboard' in (f.get('format_note') or ''): continue
                
                heights.add(h)
        return sorted(list(heights), reverse=True), info.get('title', 'Video'), info.get('uploader', 'Unknown'), info.get('duration', 0), info.get('language')

def download_video(url, path, quality_height=None):
    """Скачивает видео с YouTube с помощью yt-dlp с логикой повтора."""
    # Определяем порог для High-Res (всё, что выше 1080p, считаем High-Res)
    is_high_res = quality_height and quality_height > 1080
    
    if is_high_res:
        # Для 4K/2K используем MKV (VP9 + AAC)
        # Убираем ограничение ext=mp4 для видео
        fmt_str = f'bestvideo[height={quality_height}]+bestaudio[ext=m4a]/best[height={quality_height}]/best'
        ext = 'mkv'
        # Явно меняем расширение пути, чтобы yt-dlp не создал temp_video.mp4.mkv
        path = os.path.splitext(path)[0] + '.mkv'
    elif quality_height:
        # Для 1080p и ниже стараемся брать MP4 (H.264) для совместимости.
        # Format 397 (AV1) в MP4 может вызывать ошибки постпроцессинга на старых ffmpeg.
        # Поэтому явно приоритезируем avc (h264).
        fmt_str = (
            f'bestvideo[height={quality_height}][ext=mp4][vcodec^=avc]+bestaudio[ext=m4a]/'  # Лучший H.264
            f'bestvideo[height={quality_height}][ext=mp4]+bestaudio[ext=m4a]/'                # Любой MP4 (вкл AV1)
            f'best[height={quality_height}][ext=mp4]/'                                        # Одиночный MP4
            f'bestvideo[height={quality_height}]+bestaudio/'                                  # Fallback: любой контейнер
            f'best[height={quality_height}]'                                                  # Fallback: одиночный файл
        )
        ext = 'mp4'
    else:
        # По умолчанию тоже стараемся avc, если это mp4
        fmt_str = 'bestvideo[ext=mp4][vcodec^=avc]+bestaudio[ext=m4a]/bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'
        ext = 'mp4'

    pbar = None
    
    while True:
        try:
            pbar = tqdm(total=0, unit='B', unit_scale=True, unit_divisor=1024, 
                        desc=f"[{quality_height if quality_height else 'Best'}p]", 
                        dynamic_ncols=True, colour='blue', bar_format=CLEAN_BAR)

            def hook(d):
                if d['status'] == 'downloading':
                    try:
                        total = d.get('total_bytes') or d.get('total_bytes_estimate')
                        if total: pbar.total = int(total)
                        pbar.n = int(d.get('downloaded_bytes', 0))
                        pbar.refresh()
                    except Exception: pass
                elif d['status'] == 'finished':
                    # Просто обновляем до 100%, закрытие будет в основной функции
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
                # Важно: nopart=True предотвращает создание .part файлов.
                # Это критично для Windows, так как переименование .part файла может вызвать ошибку доступа (WinError 32),
                # если файл всё еще удерживается антивирусом или системой.
                'nopart': True,
                'nopart': True,
                'ffmpeg_location': get_binary_path('ffmpeg') or 'ffmpeg',
                'retries': 10,
                'fragment_retries': 10,
                'retry_sleep': 5,
            }

            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                if pbar and not pbar.disable:
                    pbar.close()
                return info.get('duration', 0), info.get('height', 0), path

        except (OSError, requests.exceptions.RequestException, yt_dlp.utils.DownloadError, ValueError) as e:
            if pbar and not pbar.disable:
                pbar.close()

            # Если файл скачался, но yt-dlp упал при пост-процессинге (например, парсинг ответа)
            if os.path.exists(path) and os.path.getsize(path) > 1024:
                # print(f"\n{YELLOW}⚠️ yt-dlp завершил работу с ошибкой, но файл найден.{RESET}")
                # print(f"{YELLOW}Текст ошибки: {e}{RESET}")
                # print(f"{GREEN}Продолжаем обработку скачанного файла...{RESET}")
                # Молча возвращаем успех, так как файл есть
                return 0, (quality_height if quality_height else 0), path

            error_msg = getattr(e, 'msg', str(e))
            error_msg = getattr(e, 'msg', str(e))
            
            # Если ошибка 416 (Range Not Satisfiable) или проблемы с кодеком, то продолжение невозможно.
            # Нужно удалить частично скачанные/битые файлы перед повтором.
            is_critical = "416" in error_msg or "codec parameters" in error_msg
            
            if is_critical or not ask_to_retry(f"Сетевая ошибка при скачивании видео: {error_msg}"):
                if is_critical:
                    # Если ошибка критическая для файла, спрашиваем пользователя о ПЕРЕЗАПУСКЕ с нуля
                    if ask_to_retry(f"Критическая ошибка файла ({error_msg}).\n{YELLOW}Очистить временные файлы и скачать заново?"):
                        print(f"{YELLOW}Очистка временных файлов видео...{RESET}")
                        clean_video_partials()
                        continue
                
                print(f"{RED}Завершение работы по требованию пользователя.{RESET}")
                cleanup(True)
                sys.exit(1)
                print(f"{RED}Завершение работы по требованию пользователя.{RESET}")
                cleanup(True)
                sys.exit(1)


def download_audio(url, path):
    """Скачивает аудиодорожку перевода с логикой повтора."""
    pbar = None
    while True:
        try:
            r = requests.get(url, stream=True, timeout=15)
            r.raise_for_status()
            size = int(r.headers.get('content-length', 0))
            
            pbar = tqdm(total=size, unit='iB', unit_scale=True, desc="Загрузка", 
                      dynamic_ncols=True, colour='green', bar_format=CLEAN_BAR)
            
            with open(path, 'wb') as f:
                for chunk in r.iter_content(1024):
                    pbar.update(len(chunk))
                    f.write(chunk)
            
            pbar.close()
            return # Успешное завершение

        except (OSError, requests.exceptions.RequestException) as e:
            if pbar and not pbar.disable:
                pbar.close()

            error_msg = str(e)
            if not ask_to_retry(f"Сетевая ошибка при скачивании аудио: {error_msg}"):
                print(f"{RED}Завершение работы по требованию пользователя.{RESET}")
                cleanup(True)
                sys.exit(1)

def download_youtube_audio(url, path):
    """Скачивает аудио с YouTube в формате MP3."""
    # Убираем расширение из пути для outtmpl, так как конвертер добавит .mp3
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
        'ffmpeg_location': get_binary_path('ffmpeg') or 'ffmpeg',
        'retries': 10,
        'fragment_retries': 10,
        'retry_sleep': 5,
    }

    # Прогресс-бар (упрощенный, так как тут нет merge)
    pbar = tqdm(total=0, unit='B', unit_scale=True, unit_divisor=1024, 
                desc="[Audio]", dynamic_ncols=True, colour='green', bar_format=CLEAN_BAR)
    
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
            return True
    except Exception as e:
        pbar.close()
        print(f"{RED}❌ Ошибка скачивания аудио: {e}{RESET}")
        return False

def ask_merge_mode():
    """Спрашивает пользователя о режиме объединения аудио."""
    print(f"\n{YELLOW}Выберите режим объединения:{RESET}")
    print(f"  [1] [MIX] Смешать (оригинал 20% + перевод 120%)")
    print(f"  [2] [DUAL] Две дорожки (оригинал и перевод, выбор в плеере)")
    
    while True:
        try:
            choice = input("Выбор: ").strip()
            if not choice: return 2 # Default (Mix)
            if choice == '1': return 2 # Mix (old 2)
            if choice == '2': return 3 # Dual (old 3)
        except (KeyboardInterrupt, EOFError):
            return 2

def build_ffmpeg_command(mode, final_path, is_mkv=False):
    ffmpeg_exec = get_binary_path('ffmpeg') or 'ffmpeg'
    
    base_cmd = [
        ffmpeg_exec, '-y',
        '-loglevel', 'quiet', '-progress', 'pipe:1',
        '-threads', '0', '-i', TEMP_VIDEO, '-i', TEMP_AUDIO
    ]
    
    
    # Mode 1: Translation audio ONLY (or primary), Original might be mapped but muted or not mapped? 
    # Let's interpret "Аудио с переводом" as replacement or just track 1.
    # But usually user wants to HEAR translation.
    # Previous default logic was: '-map', '0:v', '-map', '1:a', '-map', '0:a?', '-c', 'copy'
    # This maps Track 1 (Translation) as first audio, and Track 0 (Original) as second (optional).
    
    if mode == 2: # Режим 2: Смешивание (Mix)
        # filter_complex делает следующее:
        # [0:a]volume=0.2[orig] - берет звук из видео (0), уменьшает громкость до 20%, называет поток [orig]
        # [1:a]volume=1.2[dub]  - берет звук перевода (1), увеличивает громкость до 120%, называет поток [dub]
        # [orig][dub]amix...    - смешивает оба потока. duration=shortest обрезает по самой короткой дорожке (обычно видео)
        filter_complex = "[0:a]volume=0.2[orig];[1:a]volume=1.2[dub];[orig][dub]amix=inputs=2:duration=shortest[out]"
        cmd_end = [
            '-filter_complex', filter_complex,
            '-map', '0:v',        # Берем видео из источника 0 (оригинал)
            '-map', '[out]',      # Берем наш смикшированный звук
            '-c:v', 'copy',       # Видео не перекодируем (быстро)
            '-c:a', 'aac',        # Аудио кодируем в AAC (требуется для фильтра)
            '-b:a', '128k',       # Битрейт аудио
            '-strict', '-2'       # Разрешаем экспериментальные кодеки (иногда нужно для старых ffmpeg)
        ]
    elif mode == 3: # Режим 3: Две дорожки (Dual)
        cmd_end = [
            '-map', '0:v',        # Видео оригинала
            '-map', '0:a',        # Аудио оригинала (Дорожка 1)
            '-map', '1:a',        # Аудио перевода (Дорожка 2)
            '-c', 'copy',         # Всё копируем без перекодирования
            '-metadata:s:a:0', 'title=Original',
            '-metadata:s:a:0', 'handler_name=Original',
            '-metadata:s:a:1', 'title=Русский',
            '-metadata:s:a:1', 'handler_name=Русский',
            '-metadata:s:a:1', 'language=rus',
        ]
        if not is_mkv:
            cmd_end.append('-bsf:a:0')
            cmd_end.append('aac_adtstoasc')
    else: # Режим 1 (Fallback / Dub only, если вернем его)
        # Просто копируем видео и аудио перевода
        cmd_end = [
            '-map', '0:v', 
            '-map', '1:a', 
            '-map', '0:a?', # Опционально оригинал, если есть?
            '-c', 'copy',
        ]
        
    if False: # args.fast removed from helper signature, assume passed globally or ignored here? 
        # We need args here if we want to support faststart. 
        # Let's assume we add it always or pass args.
        pass
        
    cmd_end.extend(['-movflags', '+faststart']) # Always useful
    
    cmd_end.append(final_path)
    
    return base_cmd + cmd_end

def run_ffmpeg(cmd_list, duration, mode_name="FFmpeg"):
    # Для отладки заменяем quiet на error
    try:
        idx = cmd_list.index('-loglevel')
        if cmd_list[idx + 1] == 'quiet':
            cmd_list[idx + 1] = 'error'
    except (ValueError, IndexError):
        pass # -loglevel не найден или находится в конце

    try:
        # shell=False - это более безопасный способ
        # stderr=subprocess.STDOUT объединяет потоки, чтобы избежать deadlocks при переполнении буфера stderr
        proc = subprocess.Popen(cmd_list, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, 
                                universal_newlines=True, shell=False, bufsize=1, 
                                encoding='utf-8', errors='replace')
        
        fmt = "{l_bar}{bar}| {n_fmt}/{total_fmt}s"
        duration = int(duration) if duration else 100
        pbar = tqdm(total=duration, unit="s", desc=f"[{mode_name}]", dynamic_ncols=True, colour='yellow', bar_format=fmt)
        
        last = 0
        full_log = [] # Сохраняем весь вывод для отладки в случае ошибки
        
        # Читаем stdout (который теперь включает и stderr)
        while True:
            line = proc.stdout.readline()
            if not line:
                if proc.poll() is not None: break
                continue
                
            full_log.append(line)
            line_str = line.strip()
            if not line_str: continue

            # Парсинг времени
            current_sec = None
            if "out_time_us=" in line_str:
                try:
                    us = int(line_str.split('=')[1].strip())
                    current_sec = us // 1000000
                except (ValueError, IndexError): pass
            elif "out_time=" in line_str: # Fallback
                try:
                    # out_time=00:00:05.123456
                    t_str = line_str.split('=')[1].strip()
                    parts = t_str.split(':')
                    if len(parts) == 3:
                        h, m, s = int(parts[0]), int(parts[1]), float(parts[2])
                        current_sec = int(h * 3600 + m * 60 + s)
                except (ValueError, IndexError): pass

            if current_sec is not None:
                if current_sec > duration: current_sec = duration
                if current_sec > last:
                    pbar.update(current_sec - last)
                    last = current_sec
        
        rc = proc.poll()
        if rc == 0:
            # Принудительно завершаем прогресс-бар перед закрытием
            if pbar.total and pbar.n < pbar.total:
                pbar.n = pbar.total
                pbar.refresh()
        
        pbar.close()
        
        if rc != 0:
            print(f"\n{RED}❌ Ошибка FFmpeg (код {rc}):{RESET}")
            # shlex.join корректно преобразует список в строку для отображения
            print(f"{YELLOW}Команда:{RESET} {shlex.join(cmd_list)}")
            print(f"{RED}Лог выполнения:{RESET}")
            print("".join(full_log[-20:])) # Печатаем последние 20 строк лога
            cleanup(error=True)
            sys.exit(1)
            
    except (OSError, FileNotFoundError) as e:
        print(f"\n{RED}❌ Ошибка запуска FFmpeg: {e}{RESET}")
        print(f"{YELLOW}Убедитесь, что ffmpeg установлен и доступен в PATH.{RESET}")
        sys.exit(1)



def get_user_input_and_info(args):
    """Получает URL, анализирует видео и спрашивает качество."""
    url = args.url
    if not url:
        try:
            url = input(f"{CYAN}🔗 Вставьте ссылку: {RESET}").strip()
        except (EOFError, KeyboardInterrupt):
            sys.exit(0)
    
    if not url:
        print(f"{RED}❌ Ссылка не может быть пустой.{RESET}")
        sys.exit(1)
        
    validate_url(url)
    try:
        check_internet()
    except Exception as e:
        print(f"{RED}❌ Ошибка подключения: {e}{RESET}")
        sys.exit(1)

    selected_quality = args.quality
    
    # Всегда получаем информацию о видео (включая duration)
    qualities, title, uploader, duration, language = get_available_qualities(url)
    
    # Если качество указано аргументом, но его нет в списке доступных — сбрасываем выбор
    if selected_quality and selected_quality not in qualities:
        print(f"{YELLOW}⚠️ Качество {selected_quality}p недоступно для этого видео.{RESET}")
        selected_quality = None
    
    # Режим "Только аудио" может быть выбран через меню или аргументы
    if args.audio:
         selected_quality = 'audio'
    
    if not selected_quality and qualities:
        print(f"🎥 {title}")
        print(f"{YELLOW}Выберите качество:{RESET}")
        for i, q in enumerate(qualities, 1):
            print(f"  [{i}] {q}p")
        print(f"  [0] Только аудио")
        try:
            choice = input(f"Выбор [1]: ").strip()
            if choice == '0':
                selected_quality = 'audio'
            elif not choice:
                selected_quality = qualities[0]
            else:
                selected_quality = qualities[int(choice) - 1]
        except (ValueError, IndexError, EOFError, KeyboardInterrupt):
            pass 
    
    return url, selected_quality, title, uploader, duration, language

def get_translation_audio(url, duration, step_label="[1/3]"):
    """Использует vot.py для получения перевода, ожидает готовности и скачивает."""
    print(f"\n{YELLOW}{step_label} Запрос перевода...{RESET}")
    
    # Поллинг (максимум 5 минут)
    max_attempts = 30 # 30 * 10 сек = 5 минут
    for attempt in range(max_attempts):
        result = vot.translate_video(url, duration)
        
        if not result.get("success"):
            print(f"{RED}❌ Ошибка API перевода: {result.get('message')}{RESET}")
            return False
            
        status = result.get("status")
        if status == "Ready":
            audio_url = result.get("url")
            if audio_url:
                print(f"{GREEN}✅ Перевод готов!{RESET}")
                download_audio(audio_url, TEMP_AUDIO)
                return True
            else:
                 print(f"{RED}❌ Ошибка: Статус Ready, но нет URL.{RESET}")
                 return False
                 
        elif status == "Waiting":
            print(f"{YELLOW}⏳ Перевод в процессе... (Попытка {attempt+1}/{max_attempts}){RESET}")
            time.sleep(10) # Ждем 10 секунд
            
        else:
             print(f"{RED}❌ Неизвестный статус или ошибка: {result.get('message')}{RESET}")
             return False

    print(f"{RED}❌ Время ожидания перевода истекло.{RESET}")
    return False

def handle_existing_file(path):
    """Проверяет существование файла и спрашивает пользователя, что делать."""
    if not os.path.exists(path):
        return path
        
    print(f"\n{YELLOW}Файл уже существует: {path}{RESET}")
    print("  [1] Заменить")
    print("  [2] Переименовать")
    print("  [3] Отмена")
    
    while True:
        try:
            choice = input("Выбор: ").strip()
            if not choice: choice = '2' # Default Rename

            if choice == '1':
                return path
            elif choice == '2':
                base, ext = os.path.splitext(path)
                counter = 1
                new_path = f"{base} ({counter}){ext}"
                while os.path.exists(new_path):
                    counter += 1
                    new_path = f"{base} ({counter}){ext}"
                #print(f"{GREEN}Новое имя: {new_path}{RESET}")
                return new_path
            elif choice == '3':
                print(f"{YELLOW}Отмена операции.{RESET}")
                cleanup()
                sys.exit(0)
        except (KeyboardInterrupt, EOFError):
            cleanup()
            sys.exit(0)

def core_logic():
    epilog_text = """
Примеры использования:
  ytrd https://youtu.be/VIDEO_ID          # Интерактивный режим
  ytrd https://youtu.be/VIDEO_ID -m       # Режим смешивания (оригинал 20% + перевод 120%).
  ytrd https://youtu.be/VIDEO_ID -d       # Режим двух дорожек (Dual)
  ytrd https://youtu.be/VIDEO_ID -q 1080  # Скачать 1080p
    """
    
    parser = argparse.ArgumentParser(
        description="🚀 Утилита для скачивания видео с YouTube с автоматическим наложением голосового перевода.",
        epilog=epilog_text,
        formatter_class=argparse.RawTextHelpFormatter,
        add_help=False
    )
    
    # Русификация заголовков групп
    parser._positionals.title = 'Позиционные аргументы'
    parser._optionals.title = 'Опции'
    
    # Добавляем стандартный help с русским описанием
    parser.add_argument("-h", "--help", action="help", help="Показать это сообщение справки и выйти")
    
    parser.add_argument("url", nargs="?", help="Ссылка на видео YouTube.\nЕсли не указана, скрипт запросит её при запуске.")
    parser.add_argument("-o", "--output", default=OUTPUT_DIR, help=f"Папка для сохранения видео.\nПо умолчанию: {OUTPUT_DIR}")
    parser.add_argument("-m", "--mix", action="store_true", help="Режим смешивания (Mix).\nЕсли указан, оригинальная дорожка будет приглушена (20%%),\nа перевод наложен поверх (120%%).")
    parser.add_argument("-d", "--dual", action="store_true", help="Режим двух дорожек (Dual).\nСохраняет оригинальное аудио и перевод как отдельные переключаемые дорожки.")
    parser.add_argument("-q", "--quality", type=int, help="Предпочитаемое качество видео (высота строки).\nПример: 1080, 720, 480.\nЕсли не указано, будет предложен выбор.")
    parser.add_argument("-a", "--audio", action="store_true", help="Режим 'Только аудио'.\nСкачивает только переведенную аудиодорожку (mp3).")
    args = parser.parse_args()

    # --- Начальная настройка ---
    install_check()
    check_write_permissions(args.output)
    cleanup()

    # --- Шаг 1: Инфо о видео ---
    # Получаем всю информацию сразу (title, uploader, duration),
    # чтобы знать длительность видео для запроса перевода.
    # Это позволяет избежать лишних запросов и ошибок с несоответствием длины.
    url, selected_quality, title, uploader, duration, language = get_user_input_and_info(args)
    if not duration: duration = 341.0 # Fallback

    is_audio_only = (selected_quality == 'audio')
    translation_success = False
    skip_translation = False

    # Проверка языка видео
    if language and (language.startswith('ru') or language == 'Russian'):
        print(f"\n{YELLOW}⚠️  Видео определено как русскоязычное ({language}).{RESET}")
        if ask_yes_no(f"Скачать оригинал без перевода?"):
            skip_translation = True
        else:
            print(f"{YELLOW}Операция отменена.{RESET}")
            cleanup()
            return
    
    if not skip_translation:
        # Сначала пробуем получить перевод. Это наиболее вероятная точка отказа.
        label = "[1/2]" if is_audio_only else "[1/3]"
        translation_success = get_translation_audio(url, duration, label)
    
    if is_audio_only:
        if skip_translation:
             print(f"\n{YELLOW}[1/1] Загрузка оригинального аудио...{RESET}")
             name = f"{clean_name(uploader)} - {clean_name(title)} [Original].mp3"
             final_path = os.path.join(args.output, name)
             final_path = handle_existing_file(final_path)
             
             if download_youtube_audio(url, final_path):
                 print(f"\n{GREEN}✅ Готово!{RESET}")
                 print(f"📂 {final_path}")
             else:
                 print(f"{RED}❌ Не удалось скачать аудио.{RESET}")

        elif translation_success:
            print(f"\n{YELLOW}[2/2] Сохранение аудио...{RESET}")
            name = f"{clean_name(uploader)} - {clean_name(title)} [AudioTranslation].mp3"
            final_path = os.path.join(args.output, name)
            final_path = handle_existing_file(final_path)
            
            try:
                shutil.copy(TEMP_AUDIO, final_path)
                print(f"\n{GREEN}✅ Готово!{RESET}")
                print(f"📂 {final_path}")
            except Exception as e:
                print(f"{RED}❌ Не удалось сохранить аудио: {e}{RESET}")
        else:
            print(f"{RED}❌ Перевод не найден. Скачивание аудио отменено.{RESET}")
        
        cleanup()
        return

    if not translation_success and not skip_translation:
        # Перевод не найден, спрашиваем пользователя
        print(f"\n{YELLOW}⚠️ Перевод не найден.{RESET}")
        save_original = False
        while True:
            try:
                choice = input(f"Скачать оригинальное видео? (y/n): ").lower().strip()
                if choice in ('y', 'yes', 'д', 'да'):
                    save_original = True
                    break
                if choice in ('n', 'no', 'н', 'нет'):
                    break
            except (KeyboardInterrupt, EOFError):
                break
        
        if not save_original:
            cleanup()
            print("Отмена.")
            return

    # Если перевод найден (или пользователь согласился качать оригинал),
    # приступаем к загрузке видео. Используем yt-dlp с прогресс-баром.
    step_label = "[2/3]"
    if skip_translation:
        step_label = "[1/1]"
    elif not translation_success:
        step_label = "[2/2]"

    print(f"\n{YELLOW}{step_label} Загрузка видео...{RESET}")
    # duration уже получен ранее (для перевода), но yt-dlp вернет точный
    # current_path - это актуальный путь к файлу (temp_video.mkv или temp_video.mp4)
    _, actual_height, current_path = download_video(url, TEMP_VIDEO, selected_quality)
    
    # Определяем расширение из реально созданного файла
    if current_path.endswith('.mkv'):
        ext = 'mkv'
    else:
        ext = 'mp4'



    # Используем FFmpeg для объединения видео и аудио.
    # В зависимости от режима, либо просто копируем потоки, либо используем фильтр amix.
    if translation_success:
        print(f"\n{YELLOW}[3/3] Сборка файла...{RESET}")
        
        mode = 2 # Default (Mix)
        if args.mix:
            mode = 2
        elif args.dual:
            mode = 3
        else:
            mode = ask_merge_mode()
            
        # Короткие обозначения режимов
        mode_tags = {1: "Dub", 2: "Mix", 3: "Dual"}
        
        mode_str = f"[{mode_tags.get(mode, 'Dub')}]"
        mode_name = mode_tags.get(mode, 'FFmpeg').upper()
        
        # Разрешение
        res_str = f"[{actual_height}p]" if actual_height else ""
        
        # Для финального файла используем то же расширение, что и для видео
        name = f"{clean_name(uploader)} - {clean_name(title)} {res_str}{mode_str}.{ext}"
        final_path = os.path.join(args.output, name)
        
        # --- Проверка существования ---
        final_path = handle_existing_file(final_path)
        
        # Передаем актуальный путь к временному видео и флаг формата
        
        cmd_list = build_ffmpeg_command(mode, final_path, is_mkv=(ext=='mkv'))
        
        # Подмена input файла в команде (TEMP_VIDEO -> current_path)
        try:
            # TEMP_VIDEO константа "temp_video.mp4". 
            # build_ffmpeg_command добавляет её в список.
            # Находим и заменяем на реальный путь.
            idx = cmd_list.index(TEMP_VIDEO)
            cmd_list[idx] = current_path
        except ValueError:
            pass 
            
        run_ffmpeg(cmd_list, duration, mode_name)
    else:
        # Просто копируем скачанное видео
        # Если перевод не удался, режима нет (Original)
        res_str = f"[{actual_height}p]" if actual_height else ""
        name = f"{clean_name(uploader)} - {clean_name(title)} {res_str}.{ext}"
        final_path = os.path.join(args.output, name)
        
        # --- Проверка существования ---
        final_path = handle_existing_file(final_path)
        
        print(f"Копирование файла в '{final_path}'...")
        try:
            shutil.copy(current_path, final_path)
        except Exception as e:
             print(f"{RED}❌ Не удалось скопировать файл: {e}{RESET}")


    # --- Завершение ---
    cleanup()
    if os.path.exists(final_path):
        print(f"\n{GREEN}✅ Готово!{RESET}")
        print(f"📂 {final_path}")
    else:
        print(f"\n{YELLOW}Операция отменена. Временные файлы удалены.{RESET}")

def entry_point():
    """Точка входа для CLI (entry point)."""
    # Исправление кодировки для Windows консоли
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding='utf-8')

    try:
        core_logic()
    except KeyboardInterrupt:
        cleanup()
        sys.exit(0)
    except Exception as e:
        print(f"{RED}Error: {e}{RESET}")
        cleanup(True)

if __name__ == "__main__":
    entry_point()
