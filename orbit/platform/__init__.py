import sys

from orbit.platform.base import Platform


def get_platform() -> Platform:
    if sys.platform == "win32":
        from orbit.platform.windows import WindowsPlatform
        return WindowsPlatform()
    if sys.platform == "darwin":
        from orbit.platform.mac import MacPlatform
        return MacPlatform()
    raise RuntimeError(f"Unsupported platform: {sys.platform}")
