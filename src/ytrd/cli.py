import argparse
import sys
import os
from . import config
from . import utils
from . import downloader
from ytrd import __version__

def ask_to_retry(error_message):
    """Prints error message and asks user to retry."""
    print(f"\n{config.COLOR_RED}❌ {error_message}{config.COLOR_RESET}")
    while True:
        try:
            choice = input(f"{config.COLOR_YELLOW}Попробовать снова? (y/n): {config.COLOR_RESET}").lower().strip()
            if choice in ('y', 'yes', 'д', 'да'):
                return True
            if choice in ('n', 'no', 'н', 'нет'):
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
                print(f"{config.COLOR_YELLOW}Отмена операции.{config.COLOR_RESET}")
                utils.cleanup()
                sys.exit(0)
        except (KeyboardInterrupt, EOFError):
            utils.cleanup()
            sys.exit(0)

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
        
    # 2. Audio only with video options
    if args.audio and (args.mix or args.dual or args.quality):
         print(f"{config.COLOR_YELLOW}⚠️  Обнаружен конфликт аргументов (--audio с настройками видео).{config.COLOR_RESET}")
         reset_needed = True

    if reset_needed:
        print(f"{config.COLOR_YELLOW}Все аргументы сброшены. Переход в интерактивный режим.{config.COLOR_RESET}")
        args.mix = False
        args.dual = False
        args.quality = None
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
             
        print(f"{config.COLOR_RED}❌ Ошибка аргументов: {message}{config.COLOR_RESET}")
        self.print_help()
        sys.exit(2)

def parse_arguments():
    epilog_text = """
Примеры использования:
  ytrd https://youtu.be/VIDEO_ID          # Интерактивный режим
  ytrd https://youtu.be/VIDEO_ID -m       # Режим смешивания (оригинал 20% + перевод 120%).
  ytrd https://youtu.be/VIDEO_ID -d       # Режим двух дорожек (Dual)
  ytrd https://youtu.be/VIDEO_ID -q 1080  # Скачать 1080p
  ytrd https://youtu.be/VIDEO_ID -s       # Скачать с субтитрами
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
    
    args = parser.parse_args()
    return validate_args_compatibility(args)

def get_user_input_and_info(args):
    """Gets URL, analyzes video and asks for quality."""
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
    qualities, title, uploader, duration, language = downloader.get_available_qualities(url)
    
    # If quality specified by argument but not in list - reset selection
    if selected_quality and selected_quality not in qualities:
        print(f"{config.COLOR_YELLOW}⚠️ Качество {selected_quality}p недоступно для этого видео.{config.COLOR_RESET}")
        selected_quality = None
    
    # "Audio only" mode can be selected via menu or arguments
    if args.audio:
         selected_quality = 'audio'
    
    if not selected_quality and qualities:
        print(f"🎥 {title}")
        print(f"{config.COLOR_YELLOW}Выберите качество:{config.COLOR_RESET}")
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
