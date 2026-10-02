"""Package metadata for the upifraud CLI."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("risklens")
except PackageNotFoundError:  # running from source without an install
    try:
        __version__ = version("mule-hunt")
    except PackageNotFoundError:
        __version__ = "0.0.0.dev"
