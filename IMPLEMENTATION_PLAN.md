# Implementation Plan - Рефакторинг YTRD

**Дата:** 2025-12-30
**Версия:** 0.4.0-dev
**Статус:** Черновик
**Особый фокус:** Кроссплатформенность и поддержка Termux

---

## Обзор

Документ содержит детальный план реализации рекомендаций из Code Review (2025-12-30) и существующего `refactoring.md` с особым учётом кроссплатформенности, особенно для Android Termux.

## Кроссплатформенные цели

| Платформа | Статус | Приоритет задач |
|-----------|--------|-----------------|
| Android (Termux) | ✅ Основная | Высокий |
| Windows | ✅ Поддерживается | Средний |
| Linux | ✅ Поддерживается | Средний |
| macOS | ⚠️ Не протестирована | Низкий |

## Приоритеты

| Приоритет | Количество задач | Описание |
|-----------|------------------|----------|
| P0 (Критический) | 4 | Безопасность, архитектура, Termux-совместимость |
| P1 (Высокий) | 6 | Устранение технического долга |
| P2 (Средний) | 4 | Улучшение качества кода |
| P3 (Низкий) | 3 | UX и документация |

---

## Phase 1: Фундаментальные изменения (P0)

### Задача 1.1: Создать систему исключений

**Файлы:** `src/ytrd/errors.py` (новый), все модули

**Затрагиваемые файлы:**
- `src/ytrd/downloader.py` - строки 162, 174, 203
- `src/ytrd/utils.py` - строки 42, 82, 96
- `src/ytrd/cli.py` - строка 203
- `src/ytrd/vot.py` - строка 190
- `src/ytrd/ffmpeg.py` - строки 227, 233

**Действия:**

1. Создать `src/ytrd/errors.py`:
```python
"""Исключения проекта YTRD."""

class YtrdError(Exception):
    """Базовое исключение проекта."""
    pass

class YtrdNetworkError(YtrdError):
    """Ошибка сети при скачивании."""
    pass

class YtrdValidationError(YtrdError):
    """Ошибка валидации входных данных."""
    pass

class YtrdExternalToolError(YtrdError):
    """Ошибка внешнего инструмента (ffmpeg, yt-dlp)."""
    pass

class YtrdUserCancelled(YtrdError):
    """Пользователь отменил операцию."""
    pass

class YtrdConfigError(YtrdError):
    """Ошибка конфигурации."""
    pass

class YtrdPlatformError(YtrdError):
    """Ошибка, специфичная для платформы (особенно Termux)."""
    pass
```

2. Заменить `sys.exit(1)` на `raise YtrdError` в модулях:
   - `downloader.py`: замена в `download_video()`, `download_audio()`
   - `utils.py`: замена в `check_write_permissions()`, `validate_url()`, `retry_on_network_error`
   - `ffmpeg.py`: замена в `run_ffmpeg()`

3. Обновить `main.py:entry_point()`:
```python
try:
    run_pipeline()
except KeyboardInterrupt:
    utils.cleanup()
    sys.exit(0)
except YtrdUserCancelled:
    utils.cleanup()
    sys.exit(0)
except YtrdError as e:
    print(f"{config.COLOR_RED}Ошибка: {e}{config.COLOR_RESET}")
    utils.cleanup(True)
    sys.exit(1)
except Exception as e:
    print(f"{config.COLOR_RED}Неожиданная ошибка: {e}{config.COLOR_RESET}")
    utils.cleanup(True)
    sys.exit(1)
```

**Тестирование:**
- Добавить тесты для каждого типа исключения
- Проверить корректность exit codes на всех платформах
- **Специально для Termux:** проверить поведение при прерывании сигналом

**Оценка времени:** 2-3 часа

---

### Задача 1.2: Убрать циклические зависимости

**Файлы:** `src/ytrd/utils.py`, `src/ytrd/downloader.py`, `src/ytrd/vot.py`

**Проблема:**
- `utils.py` импортирует `cli.py` внутри функций
- `vot.py` зависит от `downloader.py`

**Решение - Dependency Injection:**

**1. Рефакторинг `utils.py:retry_on_network_error`:**

Было:
```python
def retry_on_network_error(func):
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except ... as e:
            from . import cli  # ← Циклическая зависимость
            if not cli.ask_to_retry(...):
```

Стало:
```python
def retry_on_network_error(retry_callback=None):
    """Декоратор с callback для повторной попытки.

    Args:
        retry_callback: Callable[[str], bool] - функция, принимающая сообщение
                       и возвращающая True для повтора.
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            while True:
                try:
                    return func(*args, **kwargs)
                except (OSError, requests.exceptions.RequestException, yt_dlp.utils.DownloadError) as e:
                    error_msg = getattr(e, 'msg', str(e))
                    if retry_callback is None or not retry_callback(f"Сетевая ошибка в '{func.__name__}': {error_msg}"):
                        raise YtrdNetworkError(f"Сетевая ошибка: {error_msg}") from e
        return wrapper
    return decorator
```

**2. Рефакторинг `vot.py`:**

Разделить ответственность:
- `vot.py` только запрашивает перевод и возвращает URL
- `main.py` вызывает `downloader.download_audio()`

Было:
```python
def get_translation_audio(url, duration, step_label="[1/3]", retry_callback=None, use_live_voice=False):
    ...
    downloader.download_audio(audio_url, config.TEMP_AUDIO_FILENAME, retry_callback=retry_callback)
    return True
```

Стало:
```python
def get_translation_audio(url: str, duration: float, use_live_voice: bool = False) -> tuple[bool, str | None]:
    """
    Запрашивает перевод и ждёт готовности.

    Returns:
        Tuple of (success: bool, audio_url: str | None)
    """
    # ... polling logic ...
    return True, audio_url
```

Обновить `main.py`:
```python
translation_success, audio_url = vot.get_translation_audio(url, duration, use_live_voice=use_live_voice)
if translation_success and audio_url:
    downloader.download_audio(audio_url, config.TEMP_AUDIO_FILENAME, retry_callback=cli.ask_to_retry)
```

**Оценка времени:** 2 часа

---

### Задача 1.3: Защитить секретный ключ с учётом Termux

**Файлы:** `src/ytrd/config.py`, `.env.example` (новый), `README.md`

**Особенность Termux:** В Termux нет обычного домашнего каталога как на десктопе, нужно учитывать的特殊路径.

**Действия:**

1. Создать `.env.example`:
```bash
# Yandex Voice-Over Translation HMAC Key
# Получите ключ из сетевого трафика браузера
VOT_HMAC_KEY=your_secret_key_here
```

2. Обновить `src/ytrd/config.py` с учётом Termux:
```python
import os
import sys
from pathlib import Path

# Определение платформы
IS_TERMUX = sys.platform.startswith('linux') and os.path.exists('/data/data/com.termux')
IS_WINDOWS = sys.platform == 'win32'
IS_LINUX = sys.platform.startswith('linux') and not IS_TERMUX
IS_MACOS = sys.platform == 'darwin'

def find_dotenv_path() -> Path | None:
    """Ищет .env файл с учётом особенностей платформы.

    Приоритет для Termux:
    1. ~/ytrd/.env (в домашней директории Termux)
    2. ~/.env
    3. Текущая директория

    Для других платформ:
    1. ~/.config/ytrd/.env
    2. ~/.env
    3. Текущая директория
    """
    cwd = Path.cwd()
    home = Path.home()

    if IS_TERMUX:
        # В Termux домашняя директория: /data/data/com.termux/files/home/
        paths = [
            home / 'ytrd' / '.env',
            home / '.env',
            cwd / '.env'
        ]
    else:
        paths = [
            home / '.config' / 'ytrd' / '.env',
            home / '.env',
            cwd / '.env'
        ]

    for path in paths:
        if path.exists():
            return path
    return None

# Попытка загрузить .env
try:
    from dotenv import load_dotenv
    dotenv_path = find_dotenv_path()
    if dotenv_path:
        load_dotenv(dotenv_path)
    else:
        load_dotenv()  # Стандартная загрузка
except ImportError:
    pass  # python-dotenv не установлен

# Ключ с fallback
DEFAULT_HMAC_KEY = 'bt8xH3VOlb4mqf0nqAibnDOoiPlXsisf'
VOT_HMAC_KEY = os.getenv('VOT_HMAC_KEY', DEFAULT_HMAC_KEY).encode()

if os.getenv('VOT_HMAC_KEY') is None:
    import warnings
    if IS_TERMUX:
        warnings.warn(
            "Используется дефолтный VOT_HMAC_KEY. "
            "Рекомендуется создать ~/ytrd/.env с VOT_HMAC_KEY"
        )
    else:
        warnings.warn(
            "Используется дефолтный VOT_HMAC_KEY. "
            "Рекомендуется установить через переменную окружения"
        )
```

3. Обновить `requirements.txt`:
```
python-dotenv>=1.0.0
```

4. Обновить `README.md` - секция "Конфигурация" с инструкциями для Termux:
```markdown
## Конфигурация

### Переменные окружения

Для настройки API ключа Yandex создайте файл `.env`:

**Android (Termux):**
```bash
mkdir -p ~/ytrd
echo "VOT_HMAC_KEY=your_key_here" > ~/ytrd/.env
```

**Windows/Linux/macOS:**
```bash
echo "VOT_HMAC_KEY=your_key_here" > ~/.config/ytrd/.env
```
```

**Оценка времени:** 1 час

---

### Задача 1.4: Улучшить кроссплатформенную работу с путями

**Файлы:** `src/ytrd/utils.py`, `src/ytrd/config.py`, все модули

**Проблемы Termux:**
- Отсутствие `/sdcard/Download` на некоторых устройствах
- Разные пути к загрузкам: `/sdcard/Download/`, `/storage/emulated/0/Download/`
- Права доступа к внешнему хранилищу

**Решение:**

1. Создать `src/ytrd/platform.py`:
```python
"""Кроссплатформенные утилиты."""

import os
import sys
import shutil
from pathlib import Path
from enum import Enum

class Platform(Enum):
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
        # Fallback для некоторых Linux дистрибутивов
        return Path.home() / 'Загрузки' if (Path.home() / 'Загрузки').exists() else download_dir

def get_binary_path(name: str) -> Path | None:
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
    """Проверяет и при необходимости запрашивает права доступа.

    Для Termux может потребоваться permission prompt.
    """
    if not path.exists():
        try:
            path.mkdir(parents=True, exist_ok=True)
        except PermissionError:
            return False

    return os.access(path, os.W_OK)

# Глобальные переменные для обратной совместимости
IS_TERMUX = detect_platform() == Platform.ANDROID_TERMUX
CURRENT_PLATFORM = detect_platform()
```

2. Обновить `src/ytrd/utils.py` - использовать новые функции:
```python
from .platform import get_default_output_dir, get_binary_path, ensure_write_permission, IS_TERMUX

def get_default_output_dir():
    """Возвращает путь к папке загрузок (обёртка для обратной совместимости)."""
    return str(platform.get_default_output_dir())

def get_binary_path(tool_name):
    """Находит бинарный файл (обёртка)."""
    path = platform.get_binary_path(tool_name)
    return str(path) if path else None

def check_write_permissions(path):
    """Проверяет права записи с учётом особенностей платформы."""
    path_obj = Path(path)

    if not path_obj.exists():
        try:
            path_obj.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            if IS_TERMUX:
                print(f"{config.COLOR_RED}❌ Не удалось создать папку.{config.COLOR_RESET}")
                print(f"{config.COLOR_YELLOW}На Android Termux убедитесь, что вы предоставили разрешение на запись.{config.COLOR_RESET}")
                sys.exit(1)
            raise

    if not os.access(path_obj, os.W_OK):
        if IS_TERMUX:
            print(f"{config.COLOR_RED}❌ Нет прав на запись.{config.COLOR_RESET}")
            print(f"{config.COLOR_YELLOW}Для Termux может потребоваться: termux-setup-storage{config.COLOR_RESET}")
        else:
            print(f"{config.COLOR_RED}❌ Нет прав на запись в {path}.{config.COLOR_RESET}")
        sys.exit(1)
```

3. Обновить все модули для использования `Path` вместо `os.path`:

Было:
```python
import os
if os.path.exists(path):
    os.remove(path)
```

Стало:
```python
from pathlib import Path
path_obj = Path(path)
if path_obj.exists():
    path_obj.unlink()
```

**Оценка времени:** 3 часа

---

## Phase 2: Устранение технического долга (P1)

### Задача 2.1: Исправить дублирование в cli.py

**Файл:** `src/ytrd/cli.py:184-185`

```python
# Было:
args.quality = None
args.quality = None  # Дублирование

# Стало:
args.quality = None
args.subtitles = False
```

**Оценка времени:** 5 минут

---

### Задача 2.2: Улучшить валидацию скачанных файлов

**Файл:** `src/ytrd/downloader.py:148-151`

```python
from .platform import IS_TERMUX

# Termux имеет ограничения на размер частично скачанных файлов
MIN_VALID_VIDEO_SIZE = 1024 * 100  # 100 KB минимум
if IS_TERMUX:
    MIN_VALID_VIDEO_SIZE = 1024 * 50  # На Android 50 KB

if os.path.exists(path):
    size = os.path.getsize(path)
    if size > MIN_VALID_VIDEO_SIZE:
        return 0, (quality_height if quality_height else 0), path
    else:
        os.remove(path)  # Удалить битый файл
        raise YtrdNetworkError(f"Скачанный файл слишком мал ({size} байт), возможно ошибка")
```

**Оценка времени:** 15 минут

---

### Задача 2.3: Вынести магические числа в config

**Файлы:** `src/ytrd/config.py`, `src/ytrd/main.py`

Добавить в `config.py`:
```python
# Значения по умолчанию
DEFAULT_VIDEO_DURATION = 341.0  # Средняя длительность видео для fallback
MIN_VALID_VIDEO_SIZE = 1024 * 100  # Минимальный размер валидного видео (100 KB)
MIN_VALID_VIDEO_SIZE_TERMUX = 1024 * 50  # Для Termux (50 KB)
MAX_FILENAME_LENGTH = 60  # Максимальная длина имени файла
MAX_FILENAME_LENGTH_TERMUX = 100  # Android поддерживает длинные имена

# Использовать
MAX_FILENAME_LENGTH = MAX_FILENAME_LENGTH_TERMUX if IS_TERMUX else MAX_FILENAME_LENGTH
```

Обновить `main.py:41`:
```python
if not duration:
    duration = config.DEFAULT_VIDEO_DURATION
```

**Оценка времени:** 15 минут

---

### Задача 2.4: Добавить type hints для публичных функций

**Файлы:** Все модули `src/ytrd/*.py`

Пример для `downloader.py`:
```python
from typing import Optional, Callable, Tuple, List, Union
from pathlib import Path

def download_video(
    url: str,
    path: Union[str, Path],
    quality_height: Optional[int] = None,
    retry_callback: Optional[Callable[[str], bool]] = None
) -> Tuple[int, int, str]:
    """Downloads video from YouTube using yt-dlp with retry logic.

    Args:
        url: YouTube video URL
        path: Output file path
        quality_height: Desired video height (1080, 720, etc.)
        retry_callback: Function to call on retry, receives error message

    Returns:
        Tuple of (duration, actual_height, output_path)

    Raises:
        YtrdNetworkError: On network errors
        YtrdValidationError: On invalid parameters
    """
```

**Особенность для Termux:** добавить специальные типы:
```python
# platform.py
PathLike = Union[str, Path]

def get_default_output_dir() -> Path:
    ...

def ensure_write_permission(path: PathLike) -> bool:
    ...
```

Приоритетные модули:
1. `platform.py` (новый)
2. `downloader.py`
3. `vot.py`
4. `ffmpeg.py`
5. `history.py`

**Оценка времени:** 3-4 часа

---

### Задача 2.5: Рефакторинг run_pipeline

**Файл:** `src/ytrd/main.py`

Разбить `run_pipeline()` (156 строк) на функции.

**Оценка времени:** 2 часа

---

## Phase 3: Улучшение качества (P2)

### Задача 3.1: Внедрить логирование с учётом Termux

**Файлы:** `src/ytrd/logger.py` (новый), `src/ytrd/main.py`

**Особенность Termux:** ANSI цвета поддерживаются, но не все терминалы их корректно отображают.

**1. Создать `src/ytrd/logger.py`:**
```python
import logging
import sys
from . import platform
from . import config

class TermuxSafeFormatter(logging.Formatter):
    """Форматтер, который безопасно работает в Termux."""

    # Проверка поддержки цветов
    COLORS = {
        'DEBUG': '\033[36m',
        'INFO': '\033[92m',
        'WARNING': '\033[93m',
        'ERROR': '\033[91m',
        'CRITICAL': '\033[95m',
    }
    RESET = '\033[0m'

    # В Termux можно отключить цвета через переменную окружения
    USE_COLORS = not platform.IS_TERMUX or os.getenv('TERMUX_ENABLE_COLORS', '1') == '1'

    def format(self, record):
        if self.USE_COLORS:
            color = self.COLORS.get(record.levelname, '')
            record.levelname = f"{color}{record.levelname}{self.RESET}"
        return super().format(record)

def setup_logging(level: int = logging.INFO) -> logging.Logger:
    """Настраивает логирование для приложения."""
    logger = logging.getLogger('ytrd')
    logger.setLevel(level)

    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)

        if platform.IS_TERMUX:
            # Упрощённый формат для Termux
            formatter = TermuxSafeFormatter('%(levelname)s: %(message)s')
        else:
            formatter = TermuxSafeFormatter('%(levelname)s: %(message)s')

        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger

# Глобальный логгер
logger = setup_logging()
```

**Оценка времени:** 2 часа

---

### Задача 3.2: Рефакторинг config.py

**Файл:** `src/ytrd/config.py`

См. задачу 1.4 - уже включает платформу-специфичные настройки.

**Оценка времени:** 2 часа

---

### Задача 3.3: Унифицировать работу с путями (уже в 1.4)

См. задачу 1.4.

---

### Задача 3.4: Улучшить обработку KeyboardInterrupt

**Файлы:** `src/ytrd/cli.py`, `src/ytrd/errors.py`

**Особенность Termux:** Ctrl+C может работать по-разному в зависимости от терминального эмулятора.

```python
def ask_yes_no(question: str) -> bool:
    """Asks question and waits for y/n answer."""
    while True:
        try:
            choice = input(f"{question} (y/n): ").lower().strip()
            if choice in ('y', 'yes', 'д', 'да'):
                return True
            if choice in ('n', 'no', 'н', 'нет'):
                return False
        except KeyboardInterrupt:
            # В Termux может приходить двойной сигнал
            raise YtrdUserCancelled("Пользователь прервал операцию")
        except EOFError:
            return False
```

**Оценка времени:** 30 минут

---

## Phase 4: UX и документация (P3)

### Задача 4.1: Улучшить README.md с секцией по Termux

Добавить/обновить секции:

```markdown
## Установка на Android (Termux)

### Специфичные шаги для Termux

1. Установите FFmpeg:
```bash
pkg install ffmpeg
```

2. Предоставьте права на хранилище (опционально):
```bash
termux-setup-storage
```

3. Создайте конфигурацию:
```bash
mkdir -p ~/ytrd
echo "VOT_HMAC_KEY=your_key" > ~/ytrd/.env
```

4. Установите пакет:
```bash
pip install .
```

### Известные проблемы Termux

- Некоторые устройства могут не иметь `/sdcard/Download/`. В этом случае файлы сохраняются в `~/downloads/`
- Цвета в выводе можно отключить: `export TERMUX_ENABLE_COLORS=0`
```

**Оценка времени:** 1.5 часа

---

### Задача 4.2: Добавить CHANGELOG.md

**Оценка времени:** 30 минут

---

### Задача 4.3: Добавить тесты для кроссплатформенности

**Файл:** `tests/test_platform.py` (новый)

```python
import pytest
from pathlib import Path
from ytrd import platform

class TestPlatformDetection:
    def test_detect_platform_termux(self, monkeypatch):
        monkeypatch.setattr('sys.platform', 'linux')
        monkeypatch.setattr('os.path.exists', lambda x: x == '/data/data/com.termux')
        assert platform.detect_platform() == platform.Platform.ANDROID_TERMUX

    def test_detect_platform_windows(self, monkeypatch):
        monkeypatch.setattr('sys.platform', 'win32')
        assert platform.detect_platform() == platform.Platform.WINDOWS

    def test_get_default_output_dir_termux(self, monkeypatch):
        # Mock Termux environment
        monkeypatch.setattr(platform, 'detect_platform', lambda: platform.Platform.ANDROID_TERMUX)
        monkeypatch.setattr('pathlib.Path.exists', lambda self: self == Path('/sdcard/Download'))
        assert platform.get_default_output_dir() == Path('/sdcard/Download')
```

**Оценка времени:** 2 часа

---

## Порядок выполнения

### Неделя 1
1. ✅ Задача 1.4: Кроссплатформенные пути (самая важная для Termux)
2. ✅ Задача 1.1: Система исключений
3. ✅ Задача 1.2: Убрать циклические зависимости

### Неделя 2
4. ✅ Задача 1.3: Защитить секретный ключ с учётом Termux
5. ✅ Задача 2.1: Исправить дублирование
6. ✅ Задача 2.2: Валидация файлов
7. ✅ Задача 2.3: Магические числа

### Неделя 3-4
8. ✅ Задача 2.4: Type hints (с учётом PathLike)
9. ✅ Задача 2.5: Рефакторинг run_pipeline
10. ✅ Задача 3.1: Логирование (Termux-safe)

### Неделя 5
11. ✅ Задача 3.2: Config рефакторинг
12. ✅ Задача 3.4: KeyboardInterrupt

### Неделя 6
13. ✅ Задача 4.1: README с Termux секцией
14. ✅ Задача 4.2: CHANGELOG
15. ✅ Задача 4.3: Тесты для platform.py

---

## Метрики успеха

После завершения рефакторинга:

- [ ] Нет `sys.exit()` вне `main.py`
- [ ] Нет циклических импортов
- [ ] Coverage тестов > 80%
- [ ] Все публичные функции имеют type hints
- [ ] Секретный ключ вынесен в .env
- [ ] Логирование вместо print() в бизнес-логике
- [ ] Функции не длиннее 50 строк
- [ ] Проходит flake8/black без ошибок
- [ ] **Работает на Android Termux без изменений**
- [ ] **Работает на Windows/Linux/macOS**
- [ ] **Правильные пути к файлам на всех платформах**

---

## Тестирование на платформах

### Android (Termux) - Основная
```bash
# Установка зависимостей
pkg install python ffmpeg

# Клонирование и установка
git clone repo
cd ytrd
pip install .

# Тесты
pytest

# Ручной тест
ytrd https://youtu.be/test
```

### Windows
```powershell
# Использовать GitHub Actions или локально
python -m pytest
ytrd https://youtu.be/test
```

### Linux
```bash
pytest
ytrd https://youtu.be/test
```

---

## Риски

| Риск | Вероятность | Влияние | Митигация |
|------|-------------|---------|-----------|
| Регрессия на Termux | Средняя | Высокое | Тестировать на реальном устройстве Termux |
| Сложность миграции config.py | Низкая | Среднее | Использовать @property для обратной совместимости |
| Разные пути загрузок | Средняя | Среднее | Множественные fallback-пути в platform.py |
| Пользователи забыли .env | Средняя | Низкое | Внятное предупреждение при запуске |

---

## Checklist для Termux

Перед релизом проверить на Termux:

- [ ] `pkg install ffmpeg` работает
- [ ] `pip install .` устанавливается без ошибок
- [ ] `ytrd https://youtu.be/test` скачивает видео
- [ ] Файл сохраняется в доступной директории
- [ ] История скачиваний работает
- [ ] Прогресс-бары отображаются корректно
- [ ] Ctrl+C прерывает выполнение корректно
- [ ] Цвета в терминале (если включены) читаемы
- [ ] `.env` файл загружается из `~/ytrd/.env`
