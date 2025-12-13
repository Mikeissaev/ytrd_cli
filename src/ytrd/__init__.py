from importlib.metadata import version, PackageNotFoundError

try:
    # Ищет версию установленного пакета 'ytrd'
    __version__ = version("ytrd")
except PackageNotFoundError:
    # Если пакет не установлен (например, вы просто запускаете скрипт локально),
    # ставим заглушку
    __version__ = "unknown"

