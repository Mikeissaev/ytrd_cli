import sys
import os
from . import config
from . import utils
from . import cli
from . import vot
from . import downloader
from . import ffmpeg

def run_pipeline():
    """Main execution pipeline (Conductor)."""
    args = cli.parse_arguments()

    # --- Initial setup ---
    utils.install_check()
    utils.check_write_permissions(args.output)
    utils.cleanup()

    # --- Step 1: Video Info ---
    # Get all info at once (title, uploader, duration),
    # to know video duration for translation request.
    url, selected_quality, title, uploader, duration, language = cli.get_user_input_and_info(args)
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
    
    if not skip_translation:
        # First try to get translation.
        label = "[1/2]" if is_audio_only else "[1/3]"
        # Call vot.get_translation_audio which handles polling and downloading
        translation_success = vot.get_translation_audio(
            url, duration, label, retry_callback=cli.ask_to_retry
        )
    
    if is_audio_only:
        # Pass callbacks to avoid circular imports in downloader
        downloader.process_audio_only(
            url, args, skip_translation, translation_success, uploader, title, 
            file_exists_callback=cli.handle_existing_file
        )
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

    # Delegate merging to ffmpeg module
    ffmpeg.process_video_merge(
        current_path, ext, translation_success, uploader, title, actual_height, args, duration
    )

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
    except Exception as e:
        print(f"{config.COLOR_RED}Error: {e}{config.COLOR_RESET}")
        utils.cleanup(True)
        sys.exit(1)

if __name__ == "__main__":
    entry_point()
