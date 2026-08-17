import os
import sys
from . import cli
from . import config
from . import downloader
from . import errors
from . import ffmpeg
from . import history
from . import logger
from . import runtime
from . import utils
from . import vot

log = logger.get_logger(__name__)


def _set_runtime_paths(ctx):
    config.TEMP_VIDEO_FILENAME = ctx.temp_video_path
    config.TEMP_AUDIO_FILENAME = ctx.temp_audio_path


def run_translation_check(args):
    """Checks translation availability for both voice types without downloading."""
    url = args.url
    if not url:
        try:
            url = input(f"{config.COLOR_CYAN}🔗 Вставьте ссылку: {config.COLOR_RESET}").strip()
        except (EOFError, KeyboardInterrupt):
            return
    if not url:
        raise errors.YtrdValidationError('Ссылка не может быть пустой.')

    utils.validate_url(url)
    try:
        utils.check_internet()
    except Exception as e:
        raise errors.YtrdNetworkError(f'Ошибка подключения: {e}')

    _, title, uploader, duration, language = downloader.get_available_qualities(url)
    if not duration:
        duration = config.DEFAULT_VIDEO_DURATION

    lang_code = utils.normalize_language_code(language)

    # Видео уже на русском — перевод не требуется (API не вызываем)
    if lang_code == 'ru':
        results = {mode: {'success': True, 'status': 'NotNeeded'} for mode in ('standard', 'live')}
        cli.print_translation_check_results(title, uploader, duration, language, results)
        return

    # Язык не поддерживается VOT API — перевод невозможен (API не вызываем)
    if lang_code and lang_code not in config.VOT_SUPPORTED_LANGS:
        message = f'язык «{lang_code}» не поддерживается (поддерживаются: {", ".join(config.VOT_SUPPORTED_LANGS)})'
        results = {mode: {'success': False, 'status': 'UnsupportedLang', 'message': message}
                   for mode in ('standard', 'live')}
        cli.print_translation_check_results(title, uploader, duration, language, results)
        raise errors.YtrdTranslationUnavailable(f'Перевод невозможен: {message}')

    results = vot.check_translation_availability(url, duration, source_lang=lang_code or 'en')
    cli.print_translation_check_results(title, uploader, duration, language, results)

    if not any(r.get('success') and r.get('status') == 'Ready' for r in results.values()):
        raise errors.YtrdTranslationUnavailable('Перевод сейчас недоступен')


def run_pipeline():
    """Main execution pipeline (Conductor)."""
    args = cli.parse_arguments()

    if args.clear_history:
        history.clear_history()
        return

    if args.check:
        run_translation_check(args)
        return

    ctx = runtime.create_runtime_context()
    cleanup_error = False
    _set_runtime_paths(ctx)

    try:
        utils.install_check()
        utils.check_write_permissions(args.output)

        url, selected_quality, title, uploader, duration, language, use_live_voice, mix_mode, dual_mode = cli.get_user_input_and_info(args)

        if history.is_in_history(url):
            print(f"\n{config.COLOR_YELLOW}⚠️  Это видео уже было скачано ранее.{config.COLOR_RESET}")
            if not cli.ask_yes_no("Продолжить скачивание?"):
                print(f"{config.COLOR_YELLOW}Отмена.{config.COLOR_RESET}")
                return

        args.mix = mix_mode
        args.dual = dual_mode

        if not duration:
            duration = config.DEFAULT_VIDEO_DURATION

        is_audio_only = selected_quality == 'audio'
        translation_success = False
        skip_translation = False

        if language and (language.startswith('ru') or language == 'Russian'):
            print(f"\n{config.COLOR_YELLOW}⚠️  Видео определено как русскоязычное ({language}).{config.COLOR_RESET}")
            if cli.ask_yes_no("Скачать оригинал без перевода?"):
                skip_translation = True
            else:
                print(f"{config.COLOR_YELLOW}Операция отменена.{config.COLOR_RESET}")
                return

        download_subs = bool(args.subtitles)

        if not skip_translation:
            try:
                source_lang = utils.normalize_language_code(language) or 'en'
                translation_success, audio_url = vot.get_translation_audio(
                    url, duration, use_live_voice=use_live_voice, source_lang=source_lang
                )
            except errors.YtrdTranslationUnavailable:
                translation_success, audio_url = False, None

            if translation_success and audio_url:
                print(f"\n{config.COLOR_YELLOW}[2/3] Загрузка аудио перевода...{config.COLOR_RESET}")
                try:
                    downloader.download_audio(audio_url, config.TEMP_AUDIO_FILENAME, retry_callback=cli.ask_to_retry)
                except errors.YtrdUserCancelled:
                    raise
                except errors.YtrdError:
                    translation_success = False

        if is_audio_only:
            downloader.process_audio_only(
                url, args, skip_translation, translation_success, uploader, title,
                file_exists_callback=cli.handle_existing_file
            )
            history.add_to_history(url)
            return

        if not translation_success and not skip_translation:
            print(f"\n{config.COLOR_YELLOW}⚠️ Перевод не найден.{config.COLOR_RESET}")
            if not cli.ask_yes_no("Скачать оригинальное видео?"):
                print("Отмена.")
                return

        step_label = "[2/3]"
        if skip_translation:
            step_label = "[1/1]"
        elif not translation_success:
            step_label = "[2/2]"

        print(f"\n{config.COLOR_YELLOW}{step_label} Загрузка видео...{config.COLOR_RESET}")

        _, actual_height, current_path = downloader.download_video(
            url,
            config.TEMP_VIDEO_FILENAME,
            selected_quality,
            retry_callback=cli.ask_to_retry,
            work_dir=ctx.work_dir,
        )

        ext = 'mkv' if current_path.endswith('.mkv') else 'mp4'

        sub_path = None
        sub_lang = None
        if download_subs:
            video_base = os.path.splitext(config.TEMP_VIDEO_FILENAME)[0]
            sub_path, sub_lang = downloader.download_subtitles(url, video_base)

            if sub_path:
                print(f"{config.COLOR_GREEN}✅ Субтитры найдены: {sub_path}{config.COLOR_RESET}")
            else:
                print(f"{config.COLOR_YELLOW}⚠️ Субтитры не были скачаны (возможно отсутствуют или ошибка доступа).{config.COLOR_RESET}")
                action = cli.ask_subtitle_error_action()
                if action == 'retry':
                    sub_path, sub_lang = downloader.download_subtitles(url, video_base)
                    if sub_path:
                        print(f"{config.COLOR_GREEN}✅ Субтитры найдены: {sub_path}{config.COLOR_RESET}")
                elif action == 'retry_with_cookies':
                    cookies_path = cli.ask_cookies_path()
                    if cookies_path:
                        sub_path, sub_lang = downloader.download_subtitles(url, video_base, cookies_path=cookies_path)
                        if sub_path:
                            print(f"{config.COLOR_GREEN}✅ Субтитры найдены: {sub_path}{config.COLOR_RESET}")
                        else:
                            print(f"{config.COLOR_YELLOW}⚠️ Не удалось скачать даже с cookies.{config.COLOR_RESET}")
                elif action == 'cancel':
                    print(f"{config.COLOR_YELLOW}Операция отменена пользователем.{config.COLOR_RESET}")
                    raise errors.YtrdUserCancelled("Отмена пользователем")

        ffmpeg.process_video_merge(
            current_path, ext, translation_success, uploader, title, actual_height, args, duration,
            sub_path=sub_path, sub_lang=sub_lang if sub_path else None
        )
        history.add_to_history(url)
    except errors.YtrdUserCancelled:
        raise
    except Exception:
        cleanup_error = True
        raise
    finally:
        utils.cleanup(ctx.work_dir, error=cleanup_error)


def entry_point():
    """CLI entry point."""
    logger.setup_logging()

    try:
        if sys.platform == "win32":
            sys.stdout.reconfigure(encoding='utf-8')

        os.environ["PATH"] = f"{config.TERMUX_BIN_PATH}:{os.environ.get('PATH', '')}"

        log.info("Application entry point called")
        run_pipeline()
    except KeyboardInterrupt:
        log.info("User interrupted (KeyboardInterrupt)")
        utils.cleanup()
        sys.exit(0)
    except errors.YtrdUserCancelled as e:
        log.info(f"User cancelled: {e}")
        utils.cleanup()
        sys.exit(0)
    except errors.YtrdError as e:
        log.error(f"Application error: {type(e).__name__}: {e}", exc_info=True)
        print(f"{config.COLOR_RED}❌ Ошибка: {e}{config.COLOR_RESET}")
        utils.cleanup(True)
        sys.exit(1)
    except Exception as e:
        log.critical(f"Unexpected error: {type(e).__name__}: {e}", exc_info=True)
        print(f"{config.COLOR_RED}❌ Неожиданная ошибка: {e}{config.COLOR_RESET}")
        utils.cleanup(True)
        sys.exit(1)
    finally:
        logger.shutdown_logging()


if __name__ == "__main__":
    entry_point()
