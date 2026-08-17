import argparse
import sys
import os
from . import config
from . import utils
from . import downloader
from . import errors
from . import logger
from ytrd import __version__

# Инициализация логгера для модуля cli
log = logger.get_logger(__name__)

def ask_to_retry(error_message):
    """Prints error message and asks user to retry."""
    print(f"\n{config.COLOR_RED}❌ {error_message}{config.COLOR_RESET}")
    
    # Special handling for 403 Forbidden or Format not available
    is_forbidden = "403" in error_message or "Forbidden" in error_message
    is_format_error = "Requested format is not available" in error_message
    
    while True:
        try:
            prompt = f"{config.COLOR_YELLOW}Попробовать снова? (y/n"
            if is_forbidden or is_format_error:
                prompt += "/c - cookies"
            if is_format_error and os.path.exists(config.COOKIES_FILE_PATH):
                prompt += "/x - delete cookies and retry"
            prompt += f"): {config.COLOR_RESET}"
            
            choice = input(prompt).lower().strip()
            
            if choice in ('y', 'yes', 'д', 'да'):
                return True
            if choice in ('n', 'no', 'н', 'нет'):
                return False
            if (is_forbidden or is_format_error) and (choice in ('c', 'cookies', 'с')):
                # Ask for cookies and then retry
                cookies_path = ask_cookies_path()
                return bool(cookies_path)
            if is_format_error and choice == 'x':
                try:
                    os.remove(config.COOKIES_FILE_PATH)
                    print(f"{config.COLOR_YELLOW}Cookies удалены. Повторная попытка...{config.COLOR_RESET}")
                    return True
                except OSError:
                    return False
        except (KeyboardInterrupt, EOFError):
            return False

def ask_yes_no(question):
    """Asks question and waits for y/n answer."""
    while True:
        try:
            choice = input(f"{question} (y/n): ").lower().strip()
            if choice in ('y', 'yes', 'д', 'да'):
                return True
            if choice in ('n', 'no', 'н', 'нет'):
                return False
        except (KeyboardInterrupt, EOFError):
            return False

def ask_merge_mode():
    """Asks user about audio merge mode."""
    print(f"\n{config.COLOR_YELLOW}Выберите режим объединения:{config.COLOR_RESET}")
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

def handle_existing_file(path):
    """Checks file existence and asks user what to do."""
    if not os.path.exists(path):
        return path

    print(f"\n{config.COLOR_YELLOW}Файл уже существует: {path}{config.COLOR_RESET}")
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
                return new_path
            elif choice == '3':
                raise errors.YtrdUserCancelled("Отмена операции")
        except (KeyboardInterrupt, EOFError):
            raise errors.YtrdUserCancelled("Отмена пользователем")

def ask_subtitle_error_action():
    """Asks user what to do if subtitle download fails."""
    print(f"\n{config.COLOR_YELLOW}Не удалось скачать субтитры. Действия:{config.COLOR_RESET}")
    print("  [1] Попробовать снова")
    print("  [2] Использовать cookies (для обхода rate limiting)")
    print("  [3] Продолжить без субтитров")
    print("  [4] Отмена")
    
    while True:
        try:
            choice = input("Выбор: ").strip()
            if not choice: continue
            
            if choice == '1':
                return 'retry'
            elif choice == '2':
                return 'retry_with_cookies'
            elif choice == '3':
                return 'skip'
            elif choice == '4':
                return 'cancel'
        except (KeyboardInterrupt, EOFError):
            return 'cancel'

def ask_cookies_path():
    """Asks user for cookies file path or direct paste."""
    print(f"\n{config.COLOR_CYAN}Укажите путь к файлу cookies или вставьте содержимое (Ctrl+V):{config.COLOR_RESET}")
    print(f"{config.COLOR_YELLOW}• Путь к файлу: C:\\\\cookies.txt{config.COLOR_RESET}")
    print(f"{config.COLOR_YELLOW}• Или вставьте cookies (многострочный ввод, Enter дважды для завершения){config.COLOR_RESET}")
    
    while True:
        try:
            first_line = input("Ввод: ").strip().strip('"').strip("'")
            if not first_line:
                continue
            
            # Check if it's a file path
            if os.path.exists(first_line):
                # Copy to persistent location for future use
                try:
                    import shutil
                    shutil.copy(first_line, config.COOKIES_FILE_PATH)
                    print(f"{config.COLOR_GREEN}✅ Cookies сохранены для дальнейшего использования.{config.COLOR_RESET}")
                except Exception as e:
                    print(f"{config.COLOR_YELLOW}⚠️ Не удалось сохранить cookies: {e}{config.COLOR_RESET}")
                return first_line
            
            # Check if it looks like cookies content (starts with # Netscape HTTP Cookie File or contains tab-separated values)
            if first_line.startswith("#") or "\t" in first_line:
                print(f"{config.COLOR_YELLOW}Обнаружен ввод cookies. Продолжайте вставку (Enter дважды для завершения):{config.COLOR_RESET}")
                
                lines = [first_line]
                empty_count = 0
                
                while True:
                    try:
                        line = input()
                        if not line.strip():
                            empty_count += 1
                            if empty_count >= 2:
                                break
                        else:
                            empty_count = 0
                            lines.append(line)
                    except EOFError:
                        break
                
                # Save to persistent cookies file
                try:
                    with open(config.COOKIES_FILE_PATH, 'w', encoding='utf-8') as f:
                        f.write('\n'.join(lines))
                    
                    print(f"{config.COLOR_GREEN}✅ Cookies сохранены: {config.COOKIES_FILE_PATH}{config.COLOR_RESET}")
                    print(f"{config.COLOR_CYAN}💡 В следующий раз они будут использованы автоматически.{config.COLOR_RESET}")
                    return config.COOKIES_FILE_PATH
                except Exception as e:
                    print(f"{config.COLOR_RED}❌ Не удалось сохранить cookies: {e}{config.COLOR_RESET}")
                    return None
            else:
                print(f"{config.COLOR_RED}❌ Файл не найден и это не похоже на cookies. Попробуйте снова.{config.COLOR_RESET}")
        except (KeyboardInterrupt, EOFError):
            return None


def validate_args_compatibility(args):
    """Checks arguments compatibility. If conflict exists, resets them."""
    reset_needed = False
    
    # 1. Mixing and Dual simultaneously
    if args.mix and args.dual:
        print(f"{config.COLOR_YELLOW}⚠️  Обнаружен конфликт аргументов (--mix и --dual).{config.COLOR_RESET}")
        reset_needed = True
        
    # 2. Audio only with video options or subtitles
    if args.audio and (args.mix or args.dual or args.quality or args.subtitles):
         print(f"{config.COLOR_YELLOW}⚠️  Обнаружен конфликт аргументов (--audio с настройками видео или субтитрами).{config.COLOR_RESET}")
         reset_needed = True

    if reset_needed:
        print(f"{config.COLOR_YELLOW}Все аргументы сброшены. Переход в интерактивный режим.{config.COLOR_RESET}")
        args.mix = False
        args.dual = False
        args.quality = None
        args.audio = False
        args.subtitles = False
    return args

class RussianArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        """Custom error handler for argparse"""
        # Basic translation of common argparse errors
        if "unrecognized arguments" in message:
            message = message.replace("unrecognized arguments", "Неизвестные аргументы")
        elif "the following arguments are required" in message:
             message = message.replace("the following arguments are required", "Необходимы следующие аргументы")
        elif "invalid" in message:
             message = message.replace("invalid", "некорректное").replace("value", "значение").replace("int", "число")

        raise errors.YtrdValidationError(f"Ошибка аргументов: {message}")

def parse_arguments():
    log.debug("Parsing command-line arguments")
    epilog_text = """
Примеры использования:
  ytrd https://youtu.be/VIDEO_ID          # Интерактивный режим
  ytrd https://youtu.be/VIDEO_ID -m       # Режим смешивания (оригинал 20% + перевод 120%).
  ytrd https://youtu.be/VIDEO_ID -d       # Режим двух дорожек (Dual)
  ytrd https://youtu.be/VIDEO_ID -q 1080  # Скачать 1080p
  ytrd https://youtu.be/VIDEO_ID -s       # Скачать с субтитрами
  ytrd https://youtu.be/VIDEO_ID --check  # Проверить доступность перевода без скачивания
  ytrd --clear-history                    # Очистить историю скачиваний
    """

    parser = RussianArgumentParser(
        description="🚀 Утилита для скачивания видео с YouTube с автоматическим наложением голосового перевода.",
        epilog=epilog_text,
        formatter_class=argparse.RawTextHelpFormatter,
        add_help=False
    )

    # Russify group headers
    parser._positionals.title = 'Позиционные аргументы'
    parser._optionals.title = 'Опции'

    # Add standard help with Russian description
    parser.add_argument("-h", "--help", action="help", help="Показать это сообщение справки и выйти")
    parser.add_argument("-v", "--version", action="version", version=f"ytrd {__version__}", help="Показать версию программы и выйти")

    parser.add_argument("url", nargs="?", help="Ссылка на видео YouTube.\nЕсли не указана, скрипт запросит её при запуске.")
    parser.add_argument("-o", "--output", default=utils.get_default_output_dir(), help=f"Папка для сохранения видео.\nПо умолчанию: {utils.get_default_output_dir()}")
    parser.add_argument("-m", "--mix", action="store_true", help="Режим смешивания (Mix).\nЕсли указан, оригинальная дорожка будет приглушена (20%%),\nа перевод наложен поверх (120%%).")
    parser.add_argument("-d", "--dual", action="store_true", help="Режим двух дорожек (Dual).\nСохраняет оригинальное аудио и перевод как отдельные переключаемые дорожки.")
    parser.add_argument("-q", "--quality", type=int, help="Предпочитаемое качество видео (высота строки).\nПример: 1080, 720, 480.\nЕсли не указано, будет предложен выбор.")
    parser.add_argument("-a", "--audio", action="store_true", help="Режим 'Только аудио'.\nСкачивает только переведенную аудиодорожку (mp3).")
    parser.add_argument("-s", "--subtitles", action="store_true", help="Скачать и вшить русские субтитры (если доступны).")
    parser.add_argument("-l", "--live", action="store_true", help="Использовать 'Живой голос'.\nБолее качественная и естественная озвучка.")
    parser.add_argument("--check", action="store_true", help="Проверить доступность перевода (обычный и живой голос)\nбез скачивания и выйти.")
    parser.add_argument("--clear-history", action="store_true", help="Очистить файл истории скачиваний и выйти.")

    args = parser.parse_args()
    log.debug(f"Arguments parsed: url={args.url}, output={args.output}, mix={args.mix}, dual={args.dual}, quality={args.quality}, audio={args.audio}, subtitles={args.subtitles}, live={args.live}")
    return validate_args_compatibility(args)

def print_translation_check_results(title, uploader, duration, language, results):
    """Prints formatted translation availability results for both voice types."""
    def format_status(result):
        status = result.get('status')
        if result.get('success') and status == 'Ready':
            return f"{config.COLOR_GREEN}✅ доступен{config.COLOR_RESET}"
        if result.get('success') and status == 'Waiting':
            return f"{config.COLOR_YELLOW}⏳ готовится (попробуйте позже){config.COLOR_RESET}"
        if status == 'NotNeeded':
            return f"{config.COLOR_CYAN}ℹ️  не требуется (видео уже на русском){config.COLOR_RESET}"
        if status == 'UnsupportedLang':
            message = result.get('message') or 'язык не поддерживается'
            return f"{config.COLOR_RED}🚫 невозможен ({message}){config.COLOR_RESET}"
        message = result.get('message') or 'неизвестная ошибка'
        return f"{config.COLOR_RED}❌ недоступен ({message}){config.COLOR_RESET}"

    minutes = int(duration // 60)
    seconds = int(duration % 60)
    print(f"\n🎥 {title}")
    print(f"👤 {uploader} | ⏱  {minutes}:{seconds:02d} | 🌐 {language or 'unknown'}")
    print(f"\n{config.COLOR_CYAN}🔍 Доступность перевода:{config.COLOR_RESET}")
    print(f"  Стандартный голос: {format_status(results.get('standard', {}))}")
    print(f"  Живой голос:       {format_status(results.get('live', {}))}")


def ask_voice_type():
    """Asks user about voice type (Standard or Live)."""
    print(f"\n{config.COLOR_YELLOW}Выберите тип озвучки:{config.COLOR_RESET}")
    print(f"  [1] Стандартный голос")
    print(f"  [2] Живой голос (Beta)")
    
    while True:
        try:
            choice = input("Выбор [1]: ").strip()
            if not choice: return False # Default Standard
            if choice == '1': return False
            if choice == '2': return True
        except (KeyboardInterrupt, EOFError):
            return False

def get_user_input_and_info(args):
    """Gets URL, analyzes video and asks for quality."""
    log.debug("Getting user input and video info")
    url = args.url
    if not url:
        try:
            url = input(f"{config.COLOR_CYAN}🔗 Вставьте ссылку: {config.COLOR_RESET}").strip()
        except (EOFError, KeyboardInterrupt):
            sys.exit(0)
    
    if not url:
        print(f"{config.COLOR_RED}❌ Ссылка не может быть пустой.{config.COLOR_RESET}")
        sys.exit(1)
        
    utils.validate_url(url)
    try:
        utils.check_internet()
    except Exception as e:
        print(f"{config.COLOR_RED}❌ Ошибка подключения: {e}{config.COLOR_RESET}")
        sys.exit(1)

    selected_quality = args.quality
    
    # Always get video info (including duration)
    # Note: get_available_qualities was moved to downloader
    qualities, title, uploader, duration, language = downloader.get_available_qualities(url, retry_callback=ask_to_retry)
    
    # If quality specified by argument but not in list - reset selection
    if selected_quality and selected_quality not in qualities:
        print(f"{config.COLOR_YELLOW}⚠️ Качество {selected_quality}p недоступно для этого видео.{config.COLOR_RESET}")
        selected_quality = None
    
    # "Audio only" mode can be selected via menu or arguments
    if args.audio:
         selected_quality = 'audio'
    
    interactive_mode = False
    if not selected_quality:
        interactive_mode = True
        print(f"🎥 {title}")
        print(f"{config.COLOR_YELLOW}Выберите качество:{config.COLOR_RESET}")
        
        # Display qualities if found, otherwise show "Best"
        if qualities:
            for i, q in enumerate(qualities, 1):
                print(f"  [{i}] {q}p")
        else:
            print(f"  [1] Лучшее качество (авто)")
            
        print(f"  [0] Только аудио")
        try:
            choice = input(f"Выбор [1]: ").strip()
            if choice == '0':
                selected_quality = 'audio'
            elif not choice or (not qualities and choice == '1'):
                selected_quality = qualities[0] if qualities else None
            else:
                selected_quality = qualities[int(choice) - 1]
        except (ValueError, IndexError, EOFError, KeyboardInterrupt):
            # Fallback to best if something goes wrong
            selected_quality = qualities[0] if qualities else None
    
    use_live_voice = args.live
    if interactive_mode and not use_live_voice:
        use_live_voice = ask_voice_type()

    mix_mode = args.mix
    dual_mode = args.dual

    # Ask for merge mode if interactive, not audio-only, and mode not specified
    if interactive_mode and selected_quality != 'audio' and not mix_mode and not dual_mode:
        mode_choice = ask_merge_mode()
        if mode_choice == 2:
            mix_mode = True
        elif mode_choice == 3:
            dual_mode = True

    log.info(f"User selected: quality={selected_quality}, live_voice={use_live_voice}, mix={mix_mode}, dual={dual_mode}")
    return url, selected_quality, title, uploader, duration, language, use_live_voice, mix_mode, dual_mode
