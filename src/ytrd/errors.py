"""
Исключения проекта YTRD.

Этот модуль определяет иерархию исключений для унифицированной
обработки ошибок в приложении.
"""


class YtrdError(Exception):
    """Базовое исключение проекта YTRD."""

    def __init__(self, message: str = "", original_error: Exception = None):
        self.message = message
        self.original_error = original_error
        super().__init__(message)

    def __str__(self) -> str:
        return self.message


class YtrdNetworkError(YtrdError):
    pass


class YtrdValidationError(YtrdError):
    pass


class YtrdExternalToolError(YtrdError):
    pass


class YtrdUserCancelled(YtrdError):
    pass


class YtrdConfigError(YtrdError):
    pass


class YtrdPlatformError(YtrdError):
    pass


class YtrdDownloadError(YtrdNetworkError):
    pass


class YtrdTranslationError(YtrdError):
    pass


class YtrdTranslationUnavailable(YtrdTranslationError):
    pass


class YtrdTranslationProtocolError(YtrdTranslationError):
    pass


class YtrdSubtitleUnavailable(YtrdError):
    pass


class YtrdFileError(YtrdError):
    pass
