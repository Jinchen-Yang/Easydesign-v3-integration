"""EasyDesign contract-first workflow package."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("easydesign")
except PackageNotFoundError:
    __version__ = "0+unknown"

__all__ = ["__version__"]
