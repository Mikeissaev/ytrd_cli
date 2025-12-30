"""
Кроссплатформенные утилиты.

Этот модуль обеспечивает абстракцию над различиями между платформами:
Android (Termux), Windows, Linux, macOS.
"""

import os
import sys
import shutil
from pathlib import Path
from enum import Enum
from typing import Optional


class Platform(Enum):
    """Поддерживаемые платформы."""
    ANDROID_TERMUX = "android_termux"
    WINDOWS = "windows"
    LINUX = "linux"
    MACOS = "macos"
    UNKNOWN = "unknown"


def detect_platform() -> Platform:
    """Определяет текущую платформу."""
    if sys.platform == 'win32':
        return Platform.WINDOWS
    elif sys.platform == 'darwin':
        return Platform.MACOS
    elif sys.platform.startswith('linux'):
        # Проверка на Termux
        if os.path.exists('/data/data/com.termux'):
            return Platform.ANDROID_TERMUX
        return Platform.LINUX
    return Platform.UNKNOWN


def get_default_output_dir() -> Path:
    """Возвращает путь к папке загрузок с учётом платформы."""
    platform = detect_platform()

    if platform == Platform.ANDROID_TERMUX:
        # Приоритет путей для Termux
        candidates = [
            Path('/sdcard/Download'),
            Path('/storage/emulated/0/Download'),
            Path('/data/data/com.termux/files/home/downloads'),
        ]
        for path in candidates:
            if path.exists() and os.access(path, os.W_OK):
                return path
        # Fallback - создать домашнюю директорию
        fallback = Path.home() / 'downloads'
        fallback.mkdir(exist_ok=True)
        return fallback

    elif platform == Platform.WINDOWS:
        return Path.home() / 'Downloads'

    else:  # Linux, macOS
        # XDG Download directory
        download_dir = Path.home() / 'Downloads'
        if download_dir.exists():
            return download_dir
        # Fallback для некоторых Linux дистрибутивов с русским языком
        downloads_ru = Path.home() / 'Загрузки'
        if downloads_ru.exists():
            return downloads_ru
        return download_dir


def get_binary_path(name: str) -> Optional[Path]:
    """Находит исполняемый файл с учётом Termux."""
    # Сначала проверяем PATH
    path = shutil.which(name)
    if path:
        return Path(path)

    # Для Termux - проверяем специальный путь
    if detect_platform() == Platform.ANDROID_TERMUX:
        termux_bin = Path('/data/data/com.termux/files/usr/bin') / name
        if termux_bin.exists():
            return termux_bin

    return None


def ensure_write_permission(path: Path) -> bool:
    """Проверяет и при необходимости создаёт директорию.

    Args:
        path: Путь к директории

    Returns:
        True если есть права на запись

    Raises:
        OSError: Если не удаётся создать директорию
    """
    if not path.exists():
        try:
            path.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            raise OSError(f"Не удалось создать папку {path}: {e}")

    return os.access(path, os.W_OK)


# Глобальные переменные для обратной совместимости и быстрого доступа
IS_TERMUX = detect_platform() == Platform.ANDROID_TERMUX
IS_WINDOWS = detect_platform() == Platform.WINDOWS
IS_LINUX = detect_platform() == Platform.LINUX
IS_MACOS = detect_platform() == Platform.MACOS
CURRENT_PLATFORM = detect_platform()

# Константы путей Termux
TERMUX_PREFIX_PATH = "/data/data/com.termux/files/usr"
TERMUX_BIN_PATH = os.path.join(TERMUX_PREFIX_PATH, "bin")
