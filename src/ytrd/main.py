import sys
import os
from . import config
from . import utils
from . import cli
from . import vot
from . import downloader
from . import ffmpeg
from . import history
from . import errors

def run_pipeline():
    """Main execution pipeline (Conductor)."""
    args = cli.parse_arguments()

    if args.clear_history:
        history.clear_history()
        return

    # --- Initial setup ---
    utils.install_check()
    utils.check_write_permissions(args.output)
    utils.cleanup()

    # --- Step 1: Video Info ---
    # Get all info at once (title, uploader, duration),
    # to know video duration for translation request.
    url, selected_quality, title, uploader, duration, language, use_live_voice, mix_mode, dual_mode = cli.get_user_input_and_info(args)
    
    # Check history
    if history.is_in_history(url):
        print(f"\n{config.COLOR_YELLOW}⚠️  Это видео уже было скачано ранее.{config.COLOR_RESET}")
        if not cli.ask_yes_no("Продолжить скачивание?"):
            print(f"{config.COLOR_YELLOW}Отмена.{config.COLOR_RESET}")
            utils.cleanup()
            return

    # Update args with interactive choices
    args.mix = mix_mode
    args.dual = dual_mode
    
    if not duration: duration = 341.0 # Fallback

    is_audio_only = (selected_quality == 'audio')
    translation_success = False
    skip_translation = False

    # Video language check
    if language and (language.startswith('ru') or language == 'Russian'):
        print(f"\n{config.COLOR_YELLOW}⚠️  Видео определено как русскоязычное ({language}).{config.COLOR_RESET}")
        if cli.ask_yes_no(f"Скачать оригинал без перевода?"):
            skip_translation = True
        else:
            print(f"{config.COLOR_YELLOW}Операция отменена.{config.COLOR_RESET}")
            utils.cleanup()
            return
    
    # Subtitles logic (Ask upfront)
    download_subs = False
    if args.subtitles:
        download_subs = True

    translation_success = False
    if not skip_translation:
        # Запрос перевода (vot теперь только возвращает URL)
        translation_success, audio_url = vot.get_translation_audio(
            url, duration, use_live_voice=use_live_voice
        )
        # Скачивание перевода теперь здесь
        if translation_success and audio_url:
            print(f"\n{config.COLOR_YELLOW}[2/3] Загрузка аудио перевода...{config.COLOR_RESET}")
            try:
                downloader.download_audio(audio_url, config.TEMP_AUDIO_FILENAME, retry_callback=cli.ask_to_retry)
            except errors.YtrdError:
                translation_success = False
    
    if is_audio_only:
        # Pass callbacks to avoid circular imports in downloader
        downloader.process_audio_only(
            url, args, skip_translation, translation_success, uploader, title, 
            file_exists_callback=cli.handle_existing_file
        )
        history.add_to_history(url)
        return

    if not translation_success and not skip_translation:
        # Translation not found, ask user
        print(f"\n{config.COLOR_YELLOW}⚠️ Перевод не найден.{config.COLOR_RESET}")
        save_original = False
        if cli.ask_yes_no("Скачать оригинальное видео?"):
            save_original = True
        
        if not save_original:
            utils.cleanup()
            print("Отмена.")
            return

    # If translation found (or user agreed to download original),
    # proceed with video download.
    step_label = "[2/3]"
    if skip_translation:
        step_label = "[1/1]"
    elif not translation_success:
        step_label = "[2/2]"

    print(f"\n{config.COLOR_YELLOW}{step_label} Загрузка видео...{config.COLOR_RESET}")
    
    _, actual_height, current_path = downloader.download_video(
        url, config.TEMP_VIDEO_FILENAME, selected_quality, retry_callback=cli.ask_to_retry
    )
    
    # Determine extension from actually created file
    if current_path.endswith('.mkv'):
        ext = 'mkv'
    else:
        ext = 'mp4'

    # Check for subtitles
    sub_path = None
    if download_subs:
        # Separate step for subtitles to handle 429/403 errors gracefully
        # Use base name without extension for subtitle search
        video_base = os.path.splitext(config.TEMP_VIDEO_FILENAME)[0]
        
        sub_path, sub_lang = downloader.download_subtitles(url, video_base)
        
        if sub_path:
            print(f"{config.COLOR_GREEN}✅ Субтитры найдены: {sub_path}{config.COLOR_RESET}")
        else:
            print(f"{config.COLOR_YELLOW}⚠️ Субтитры не были скачаны (возможно отсутствуют или ошибка доступа).{config.COLOR_RESET}")
            
            action = cli.ask_subtitle_error_action()
            if action == 'retry':
                # Try one more time manually
                sub_path, sub_lang = downloader.download_subtitles(url, video_base)
                if sub_path:
                    print(f"{config.COLOR_GREEN}✅ Субтитры найдены: {sub_path}{config.COLOR_RESET}")
            elif action == 'retry_with_cookies':
                # Ask for cookies path and retry
                cookies_path = cli.ask_cookies_path()
                if cookies_path:
                    sub_path, sub_lang = downloader.download_subtitles(url, video_base, cookies_path=cookies_path)
                    if sub_path:
                        print(f"{config.COLOR_GREEN}✅ Субтитры найдены: {sub_path}{config.COLOR_RESET}")
                    else:
                        print(f"{config.COLOR_YELLOW}⚠️ Не удалось скачать даже с cookies.{config.COLOR_RESET}")
            elif action == 'skip':
                sub_path = None
            elif action == 'cancel':
                print(f"{config.COLOR_YELLOW}Операция отменена пользователем.{config.COLOR_RESET}")
                raise errors.YtrdUserCancelled("Отмена пользователем")


    # Delegate merging to ffmpeg module
    ffmpeg.process_video_merge(
        current_path, ext, translation_success, uploader, title, actual_height, args, duration, 
        sub_path=sub_path, sub_lang=sub_lang if sub_path else None
    )
    
    # Add to history if successful
    history.add_to_history(url)

def entry_point():
    """CLI entry point."""
    # Fix encoding for Windows console
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding='utf-8')

    # Add Termux paths
    os.environ["PATH"] = f"{config.TERMUX_BIN_PATH}:{os.environ.get('PATH', '')}"

    try:
        run_pipeline()
    except KeyboardInterrupt:
        utils.cleanup()
        sys.exit(0)
    except errors.YtrdUserCancelled as e:
        # Пользователь отменил операцию - тихий выход
        utils.cleanup()
        sys.exit(0)
    except errors.YtrdError as e:
        # Ошибки приложения - показать сообщение и выйти с кодом 1
        print(f"{config.COLOR_RED}❌ Ошибка: {e}{config.COLOR_RESET}")
        utils.cleanup(True)
        sys.exit(1)
    except Exception as e:
        # Неожиданные ошибки
        print(f"{config.COLOR_RED}❌ Неожиданная ошибка: {e}{config.COLOR_RESET}")
        utils.cleanup(True)
        sys.exit(1)

if __name__ == "__main__":
    entry_point()
