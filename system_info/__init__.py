"""system_info: in-depth Linux system information collector (GUI-ready)."""

from .app import ALL_COLLECTORS, SystemInfoApp
from .core import CategoryResult, Field, SystemSnapshot

__all__ = ["SystemInfoApp", "ALL_COLLECTORS", "SystemSnapshot", "CategoryResult", "Field"]
__version__ = "1.2.0"
