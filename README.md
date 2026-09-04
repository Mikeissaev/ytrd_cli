# ytrd

[![CI](https://github.com/id-ex/ytrd/actions/workflows/ci.yml/badge.svg)](https://github.com/id-ex/ytrd/actions/workflows/ci.yml)

[English](#english) · [Русский](#русский)

<a id="english"></a>

## English

**ytrd** is a cross-platform command-line tool that downloads YouTube videos and adds a Russian voice-over track provided by the Yandex Voice-Over Translation service.

It supports Linux, Windows, macOS, and Android through Termux.

### Features

- automated `yt-dlp` → voice-over → FFmpeg processing pipeline;
- standard voice-over and Yandex Live Voice modes;
- **Mix** mode with the original and translated audio combined;
- **Dual** mode with separate selectable audio tracks;
- translated audio-only MP3 downloads;
- selectable video quality with H.264 compatibility preference;
- embedded subtitles with Russian-to-English fallback;
- cookies support for restricted YouTube content;
- network retries, download history, file logging, and isolated temporary workspaces;
- translation availability check without downloading the video.

### Requirements

- Python 3.8 or newer;
- FFmpeg available in `PATH`;
- an internet connection.

### Installation

```bash
git clone https://github.com/id-ex/ytrd.git
cd ytrd
python -m pip install .
```

### Quick start

Run the interactive downloader:

```bash
ytrd "https://youtu.be/VIDEO_ID"
```

Choose a mode directly:

```bash
ytrd "https://youtu.be/VIDEO_ID" --mix
ytrd "https://youtu.be/VIDEO_ID" --dual --quality 1080
ytrd "https://youtu.be/VIDEO_ID" --audio
ytrd "https://youtu.be/VIDEO_ID" --subtitles
```

Check whether standard and Live Voice translations are available without downloading:

```bash
ytrd "https://youtu.be/VIDEO_ID" --check
```

For the complete installation, configuration, cookies, and CLI reference, see the [Russian documentation](#русский) below.

> [!NOTE]
> This project uses an unofficial Yandex Voice-Over Translation interface and is not affiliated with or endorsed by Yandex or YouTube. Availability may change without notice. Users are responsible for complying with the applicable platform terms and copyright laws.

---

<a id="русский"></a>

## Русский

CLI-утилита для скачивания видео с YouTube с автоматическим добавлением русской закадровой озвучки через Yandex Voice-Over Translation API.

Поддерживаются Linux, Windows, macOS и Android Termux.

## Возможности

- скачивание видео с YouTube через `yt-dlp`;
- получение русской аудиодорожки перевода;
- стандартный голос и режим Yandex Live Voice;
- режим **Mix**:
  - оригинальная дорожка — 20%;
  - аудиодорожка перевода — 120%;
- режим **Dual**:
  - оригинальная дорожка;
  - аудиодорожка перевода;
- скачивание только аудиодорожки перевода в MP3;
- выбор качества видео;
- приоритет H.264 для лучшей совместимости;
- использование MKV для видео выше 1080p;
- скачивание и встраивание субтитров;
- поиск русских субтитров с fallback на английские;
- поддержка cookies при ограничениях YouTube;
- автоматические повторы сетевых операций;
- история скачанных ссылок;
- проверка существующих файлов;
- отдельная временная директория для каждого запуска;
- файловое логирование работы приложения.

## Требования

### Обязательные компоненты

- Python 3.8 или новее;
- FFmpeg;
- доступ к интернету.

### Python-зависимости

Проект использует:

- `requests` — HTTP-запросы к API и загрузка аудио;
- `yt-dlp` — получение информации и скачивание видео;
- `tqdm` — отображение прогресса операций.

Все зависимости устанавливаются автоматически вместе с проектом.

## Установка

### Linux

Установите необходимые системные пакеты:

```bash
sudo apt update
sudo apt install -y python3 python3-pip ffmpeg git
```

Скачайте проект:

```bash
git clone https://github.com/id-ex/ytrd.git
cd ytrd
```

Установите программу:

```bash
python3 -m pip install .
```

Проверьте установку:

```bash
ytrd --version
```

### Windows

Установите Python и FFmpeg:

```powershell
winget install Python.Python.3
winget install Gyan.FFmpeg
```

Скачайте и установите проект:

```powershell
git clone https://github.com/id-ex/ytrd.git
cd ytrd
py -m pip install .
```

Проверьте установку:

```powershell
ytrd --version
```

### Android Termux

Установите необходимые пакеты:

```bash
pkg update
pkg install python ffmpeg git
```

Для доступа к общей памяти Android выполните:

```bash
termux-setup-storage
```

Скачайте и установите проект:

```bash
git clone https://github.com/id-ex/ytrd.git
cd ytrd
python -m pip install .
```

Для сохранения файлов в папку загрузок Android:

```bash
ytrd "https://youtu.be/VIDEO_ID" \
  -o /storage/emulated/0/Download
```

## Быстрый запуск

Интерактивный режим:

```bash
ytrd "https://youtu.be/VIDEO_ID"
```

В интерактивном режиме программа предложит выбрать:

1. качество видео;
2. тип голоса;
3. режим аудио;
4. дополнительные параметры загрузки.

## Аргументы командной строки

```text
-h, --help          Показать справку
-v, --version       Показать версию
-m, --mix           Использовать режим Mix
-d, --dual          Использовать режим Dual
-q, --quality       Указать качество видео
-a, --audio         Скачать только аудио
-s, --subtitles     Скачать и встроить субтитры
-l, --live          Использовать Live Voice
-o, --output        Указать папку сохранения
--check             Проверить доступность перевода без скачивания
--clear-history     Очистить историю загрузок
```

## Примеры использования

### Интерактивный режим

```bash
ytrd "https://youtu.be/VIDEO_ID"
```

### Режим Mix

Оригинальная дорожка приглушается, а аудиодорожка перевода накладывается поверх:

```bash
ytrd "https://youtu.be/VIDEO_ID" --mix
```

Короткий вариант:

```bash
ytrd "https://youtu.be/VIDEO_ID" -m
```

### Режим Dual

Оригинальная дорожка и аудиодорожка перевода сохраняются отдельно:

```bash
ytrd "https://youtu.be/VIDEO_ID" --dual
```

Короткий вариант:

```bash
ytrd "https://youtu.be/VIDEO_ID" -d
```

В видеоплеере можно выбрать нужную аудиодорожку.

### Выбор качества

```bash
ytrd "https://youtu.be/VIDEO_ID" -q 1080
```

Примеры качества:

```text
1080p
720p
480p
360p
```

Если указанное качество недоступно, программа предложит выбрать доступное.

### Только аудио

Скачать аудиодорожку перевода в MP3:

```bash
ytrd "https://youtu.be/VIDEO_ID" --audio
```

Короткий вариант:

```bash
ytrd "https://youtu.be/VIDEO_ID" -a
```

Для русскоязычного видео программа может предложить скачать оригинальную аудиодорожку.

### Live Voice

Использовать более качественный и естественный режим озвучки:

```bash
ytrd "https://youtu.be/VIDEO_ID" --live
```

Короткий вариант:

```bash
ytrd "https://youtu.be/VIDEO_ID" -l
```

### Субтитры

Скачать и встроить субтитры в итоговый файл:

```bash
ytrd "https://youtu.be/VIDEO_ID" --subtitles
```

Короткий вариант:

```bash
ytrd "https://youtu.be/VIDEO_ID" -s
```

Сначала программа ищет русские субтитры. Если они недоступны, используется английская версия.

### Папка сохранения

Сохранить видео в папку загрузок Android:

```bash
ytrd "https://youtu.be/VIDEO_ID" \
  -o /storage/emulated/0/Download
```

Сохранить видео в другую папку:

```bash
ytrd "https://youtu.be/VIDEO_ID" \
  -o "$HOME/Downloads"
```

### Проверка доступности перевода

Проверяет оба типа озвучки (стандартный и Live Voice) без скачивания.
Учитывает язык видео: для русскоязычных видео перевод не требуется,
а для языков вне списка поддерживаемых VOT API — невозможен.

```bash
ytrd "https://youtu.be/VIDEO_ID" --check
```

Код выхода: `0` — перевод доступен или не требуется, `1` — недоступен/невозможен.

### Очистка истории

```bash
ytrd --clear-history
```

## Конфигурация VOT

Для стабильной работы рекомендуется указать собственный ключ Yandex Voice-Over Translation API.

### Linux, macOS и Termux

Для текущего сеанса:

```bash
export VOT_HMAC_KEY="ваш_ключ"
```

Для постоянного сохранения в Bash:

```bash
echo 'export VOT_HMAC_KEY="ваш_ключ"' >> ~/.bashrc
```

Для Zsh:

```bash
echo 'export VOT_HMAC_KEY="ваш_ключ"' >> ~/.zshrc
```

### Windows PowerShell

Для текущего сеанса:

```powershell
$env:VOT_HMAC_KEY = "ваш_ключ"
```

Для постоянной настройки:

```powershell
[Environment]::SetEnvironmentVariable(
    "VOT_HMAC_KEY",
    "ваш_ключ",
    "User"
)
```

Если ключ не задан, используется ключ по умолчанию. Для стабильной работы рекомендуется использовать собственный ключ.

## Cookies

Cookies могут потребоваться при ограничениях YouTube во время загрузки субтитров.

При необходимости программа предложит:

- указать путь к файлу cookies;
- вставить содержимое cookies в терминал.

Поддерживается формат Netscape HTTP Cookie File.

Не публикуйте cookies и не добавляйте их в Git.

## История загрузок

После успешного завершения операции URL добавляется в локальную историю:

```text
~/.ytrd_history.json
```

Если ссылка уже присутствует в истории, программа предложит подтвердить повторную загрузку.

Очистить историю:

```bash
ytrd --clear-history
```

## Имена файлов

Итоговые файлы получают имя на основе автора, названия и качества видео.

Примеры:

```text
Channel - Video Title [1080p][Mix].mp4
Channel - Video Title [1080p][Dual].mp4
Channel - Video Title [AudioTranslation].mp3
Channel - Video Title [Original].mp3
```

Недопустимые для файловой системы символы удаляются автоматически.

## Временные файлы

Для каждого запуска создаётся отдельная временная директория.

В ней хранятся:

- исходное видео;
- аудиодорожка перевода;
- временные файлы субтитров;
- промежуточные результаты обработки.

После успешного завершения временные файлы удаляются.

## Структура проекта

```text
src/ytrd/
├── cli.py          # Аргументы и интерактивный интерфейс
├── config.py       # Конфигурация и константы
├── downloader.py   # Загрузка видео, аудио и субтитров
├── errors.py       # Исключения проекта
├── ffmpeg.py       # Обработка аудио, видео и субтитров
├── history.py      # История скачиваний
├── logger.py       # Логирование
├── main.py         # Точка входа и основной pipeline
├── platform.py     # Платформенная логика
├── runtime.py      # Контекст временных файлов
├── utils.py        # Вспомогательные функции
└── vot.py          # Yandex Voice-Over Translation API
```

## Лицензия

Проект распространяется под лицензией MIT.
