# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Проект

**ytrd** — утилита командной строки для скачивания YouTube видео с автоматическим наложением закадрового перевода (Yandex Voice-Over Translation).

## Команды разработки

```bash
# Установка зависимостей
pip install .

# Запуск всех тестов
pytest

# Запуск с coverage
pytest --cov=ytrd

# Запуск одного теста
pytest tests/test_module.py::test_function

# Установка FFmpeg (требуется для работы)
# Android (Termux):
pkg install ffmpeg
# Windows:
winget install Gyan.FFmpeg
# Linux:
sudo apt install ffmpeg
```

## Архитектура

### Основные модули

| Модуль | Назначение |
|--------|------------|
| `main.py` | Точка входа (`entry_point`) и оркестрация пайплайна |
| `cli.py` | Обработка аргументов CLI и интерактивный ввод |
| `downloader.py` | Скачивание видео/аудио через yt-dlp |
| `vot.py` | Интеграция с Yandex Voice-Over Translation API |
| `ffmpeg.py` | Обработка аудио/видео (сведение, наложение) |
| `history.py` | История скачиваний для предотвращения дублей |
| `platform.py` | Кроссплатформенные утилиты (особая поддержка Termux) |
| `config.py` | Конфигурация и константы |
| `utils.py` | Вспомогательные функции |
| `errors.py` | Иерархия исключений проекта |

### Пайплайн обработки

1. **Валидация URL** → `cli.parse_args()`
2. **Скачивание видео** → `downloader.download_video()`
3. **Получение перевода** → `vot.get_translation_audio()` → возвращает URL
4. **Скачивание аудио перевода** → `downloader.download_audio()`
5. **Обработка в FFmpeg** → `ffmpeg.mix_audio()` / `ffmpeg.dual_audio()`
6. **Сохранение в историю** → `history.add()`

## Важные паттерны

### Обработка ошибок

- Все исключения наследуются от `YtrdError` (определён в `errors.py`)
- **Никаких `sys.exit()` в модулях** — только в `main.py:entry_point()`
- Модули должны `raise YtrdError`, а не завершать программу

### Dependency Injection

- `retry_on_network_error` принимает `retry_callback` вместо прямого импорта `cli`
- `vot.get_translation_audio()` возвращает `(success, url)`, не скачивает файл сама
- Это устраняет циклические зависимости между модулями

### Кроссплатформенность

Проект ориентирован на **Android Termux** как основную платформу:

- `platform.IS_TERMUX` — флаг для Termux-специфичной логики
- `platform.get_default_output_dir()` — возвращает корректный путь для загрузок:
  - Termux: `/sdcard/Download/` или `~/downloads/`
  - Windows: `~/Downloads`
  - Linux/macOS: `~/Downloads` или `~/Загрузки`
- `platform.get_binary_path()` — находит исполняемые файлы с учётом Termux

### Конфигурация

- `VOT_HMAC_KEY` берётся из переменной окружения или `.env` файла
- Пути к `.env` (приоритет):
  - Termux: `~/ytrd/.env` → `~/.env` → `.`
  - Другие: `~/.config/ytrd/.env` → `~/.env` → `.`

## Git и версионирование

### Правила коммитов

- **Все коммиты на русском языке**
- Формат Conventional Commits: `<тип>: <описание в повелительном наклонении>`
- Автор: `mikeissaev <scr89shadow@gmail.com>`
- Не выполнять git-команды автоматически — только по явному запросу

### SemVer (формат MAJOR.MINOR.PATCH)

| Изменение | Версия | Когда | Тип коммита |
|-----------|--------|-------|-------------|
| PATCH | 1.2.X | Обратно совместимые фиксы | fix, perf, refactor |
| MINOR | 1.X.0 | Новый функционал | feat |
| MAJOR | X.0.0 | Breaking changes | любой с `!` |

### Типы коммитов

- `feat` — новый функционал
- `fix` — исправление багов
- `refactor` — улучшение кода (не фича/фикс)
- `style` — форматирование
- `perf` — оптимизация
- `test` — тесты
- `docs` — документация
- `build/ci` — зависимости, сборка
- `chore` — прочее
- `revert` — отмена изменений
- `!` —Breaking changes

## Режимы работы с аудио

- **Mix** (`-m`): оригинал 20% + перевод 120%
- **Dual** (`-d`): две отдельные дорожки
- **Audio-only** (`-a`): только MP3 с переводом
