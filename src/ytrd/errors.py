"""
Исключения проекта YTRD.

Этот модуль определяет иерархию исключений для унифицированной
обработки ошибок в приложении.
"""


class YtrdError(Exception):
    """Базовое исключение проекта YTRD.

    Все исключения приложения должны наследоваться от этого класса.
    """

    def __init__(self, message: str = "", original_error: Exception | None = None):
        """Инициализирует исключение.

        Args:
            message: Сообщение об ошибке
            original_error: Оригинальное исключение (для цепочек исключений)
        """
        self.message = message
        self.original_error = original_error
        super().__init__(message)

    def __str__(self) -> str:
        return self.message


class YtrdNetworkError(YtrdError):
    """Ошибка сети при скачивании или запросе к API.

    Включает ошибки HTTP, таймауты, проблемы с соединением.
    """

    pass


class YtrdValidationError(YtrdError):
    """Ошибка валидации входных данных.

    Некорректный URL, недопустимые аргументы и т.д.
    """

    pass


class YtrdExternalToolError(YtrdError):
    """Ошибка внешнего инструмента.

    Проблемы с ffmpeg, yt-dlp, отсутствующие зависимости.
    """

    pass


class YtrdUserCancelled(YtrdError):
    """Пользователь отменил операцию.

    Используется при прерывании через Ctrl+C или отказе в prompt.
    """

    pass


class YtrdConfigError(YtrdError):
    """Ошибка конфигурации.

    Проблемы с файлом конфигурации, переменными окружения,
    отсутствие необходимых настроек.
    """

    pass


class YtrdPlatformError(YtrdError):
    """Ошибка, специфичная для платформы.

    Особенности Termux, Windows, Linux и т.д.
    """

    pass


class YtrdDownloadError(YtrdNetworkError):
    """Ошибка при скачивании видео или аудио.

    Более специфичная версия YtrdNetworkError для операций скачивания.
    """

    pass


class YtrdTranslationError(YtrdError):
    """Ошибка при получении перевода.

    Проблемы с API Yandex Translation, отсутствие перевода и т.д.
    """

    pass


class YtrdFileError(YtrdError):
    """Ошибка при работе с файлами.

    Проблемы с доступом к файлам, правами записи, диском и т.д.
    """

    pass
