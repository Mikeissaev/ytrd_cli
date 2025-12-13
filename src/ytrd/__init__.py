from importlib.metadata import version, PackageNotFoundError

try:
    # Checks installed 'ytrd' package version
    __version__ = version("ytrd")
except PackageNotFoundError:
    # If package not installed (e.g. running script locally),
    # set placeholder
    __version__ = "unknown"

