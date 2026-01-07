"""
Модуль логирования ytrd.

Обеспечивает файловое логирование всех событий приложения
без вмешательства в пользовательский вывод (print()).
"""

import logging
import os
import sys
import tempfile
from pathlib import Path
from typing import Optional

from . import config
from . import platform

# Импорт версии напрямую из __init__.py
try:
    from . import __version__ as ytrd_version
except ImportError:
    ytrd_version = "unknown"


# --- Константы ---
LOG_FILE_NAME = "ytrd.log"
DEFAULT_LOG_LEVEL = logging.DEBUG
LOG_FORMAT = "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s"
DATE_FORMAT = "%Y-%m-%d %H:%M:%S"


class YtrdFileHandler(logging.FileHandler):
    """Специальный handler для корректной работы с путями на разных платформах."""

    def __init__(self, filename: str, mode: str = 'a', encoding: str = 'utf-8'):
        # Убедиться, что директория существует
        log_path = Path(filename)
        log_dir = log_path.parent
        try:
            if not log_dir.exists():
                log_dir.mkdir(parents=True, exist_ok=True)
        except OSError:
            # Fallback: использовать временную директорию
            filename = os.path.join(tempfile.gettempdir(), LOG_FILE_NAME)

        super().__init__(filename, mode, encoding)

    def handleError(self, record):
        """Игнорировать ошибки записи (например, при переполнении диска)."""
        pass


def get_log_directory() -> Path:
    """Определяет директорию для лог-файла с учётом платформы.

    Приоритет путей:
    1. YTRD_LOG_DIR из переменных окружения
    2. ~/ytrd/logs/ (Termux)
    3. ~/.config/ytrd/logs/ (Linux/macOS)
    4. ~/AppData/Local/ytrd/logs/ (Windows)
    """
    # 1. Переменная окружения имеет наивысший приоритет
    env_log_dir = os.getenv('YTRD_LOG_DIR')
    if env_log_dir:
        return Path(env_log_dir)

    # 2. Платформо-специфичные пути
    plat = platform.detect_platform()

    if plat == platform.Platform.ANDROID_TERMUX:
        # Termux: ~/ytrd/logs/
        log_dir = Path.home() / 'ytrd' / 'logs'
    elif plat == platform.Platform.WINDOWS:
        # Windows: ~/AppData/Local/ytrd/logs/
        log_dir = Path.home() / 'AppData' / 'Local' / 'ytrd' / 'logs'
    else:
        # Linux/macOS: ~/.config/ytrd/logs/
        log_dir = Path.home() / '.config' / 'ytrd' / 'logs'

    return log_dir


def get_log_level() -> int:
    """Определяет уровень логирования из переменных окружения.

    Переменная YTRD_LOG_LEVEL может принимать значения:
    DEBUG, INFO, WARNING, ERROR, CRITICAL
    """
    level_str = os.getenv('YTRD_LOG_LEVEL', 'DEBUG').upper()
    return getattr(logging, level_str, DEFAULT_LOG_LEVEL)


# --- Инициализация логгера ---
_logger: Optional[logging.Logger] = None
_handler: Optional[YtrdFileHandler] = None


def setup_logging() -> logging.Logger:
    """Инициализует файловое логирование.

    Вызывается один раз при старте приложения (в main.py:entry_point()).

    Returns:
        Настроенный экземпляр логгера.
    """
    global _logger, _handler

    if _logger is not None:
        return _logger

    # Создаём логгер
    _logger = logging.getLogger('ytrd')
    _logger.setLevel(get_log_level())

    # Определяем путь к лог-файлу
    log_dir = get_log_directory()
    log_file = log_dir / LOG_FILE_NAME

    # Создаём handler только для записи в файл
    _handler = YtrdFileHandler(str(log_file))
    _handler.setLevel(get_log_level())
    _handler.setFormatter(logging.Formatter(LOG_FORMAT, DATE_FORMAT))

    # Добавляем handler (НЕ используем StreamHandler для stdout/stderr!)
    _logger.addHandler(_handler)

    # Логируем начало сессии
    _logger.info("=" * 60)
    _logger.info(f"ytrd v{ytrd_version} started")
    _logger.info(f"Platform: {platform.CURRENT_PLATFORM.value}")
    _logger.info(f"Log file: {log_file}")
    _logger.info("=" * 60)

    return _logger


def get_logger(name: str = None) -> logging.Logger:
    """Возвращает логгер для использования в модулях.

    Args:
        name: Имя модуля (обычно __name__). Если None, возвращает корневой логгер.

    Returns:
        Экземпляр логгера.

    Пример:
        >>> from ytrd.logger import get_logger
        >>> logger = get_logger(__name__)
        >>> logger.info("Сообщение")
    """
    if _logger is None:
        setup_logging()

    if name:
        return _logger.getChild(name)
    return _logger


def shutdown_logging():
    """Корректно завершает логирование.

    Вызывается при завершении приложения (в main.py:entry_point()).
    """
    global _logger, _handler

    if _logger:
        _logger.info("=" * 60)
        _logger.info("ytrd finished")
        _logger.info("=" * 60)

    if _handler:
        _handler.close()

    if _logger:
        for handler in _logger.handlers[:]:
            _logger.removeHandler(handler)

    _logger = None
    _handler = None
