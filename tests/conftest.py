"""
Shared pytest configuration for the OsdagBridge test suite.

Headless Qt support
-------------------
The sandbox lacks the system ``libEGL.so.1`` (glvnd) package and there is no
root access to install it, while PySide6's ``libQt6Gui`` links against EGL
with immediate binding.  ``_qt_prepare_egl_stub()`` below therefore preloads
a tiny no-op EGL stub *before* any PySide6 import so the offscreen QPA
platform (``QT_QPA_PLATFORM=offscreen``) works without a display.

On machines that already provide a real ``libEGL.so.1`` the stub is never
used.  Qt-based tests still degrade gracefully: when PySide6 cannot be
imported at all they are skipped via :func:`qt_modules_available`.
"""

import ctypes
import os
import subprocess
import sys

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_STUB_DIR = os.path.join(_HERE, "_qt_stubs")
_STUB_SO = os.path.join(_STUB_DIR, "libEGL.so.1")
_STUB_SRC = os.path.join(_STUB_DIR, "egl_stub.c")

_qt_egl_stub_loaded = False


def _system_egl_available() -> bool:
    try:
        ctypes.CDLL("libEGL.so.1")
        return True
    except OSError:
        return False


def _build_egl_stub() -> bool:
    """Compile the no-op EGL stub (only used when no system EGL exists)."""
    if not (os.path.isfile(_STUB_SRC) and os.access(_STUB_SRC, os.R_OK)):
        return False
    cc = os.environ.get("CC") or "cc"
    try:
        subprocess.run(
            [cc, "-shared", "-fPIC", "-Wl,-soname,libEGL.so.1",
             "-o", _STUB_SO, _STUB_SRC],
            check=True, capture_output=True, timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return os.path.isfile(_STUB_SO)


def _qt_prepare_egl_stub() -> bool:
    """Preload the EGL stub so PySide6 can be imported headlessly."""
    global _qt_egl_stub_loaded
    if _qt_egl_stub_loaded or _system_egl_available():
        _qt_egl_stub_loaded = True
        return True
    if not os.path.isfile(_STUB_SO) and not _build_egl_stub():
        return False
    try:
        ctypes.CDLL(_STUB_SO, mode=ctypes.RTLD_GLOBAL)
    except OSError:
        return False
    _qt_egl_stub_loaded = True
    return True


def qt_modules_available():
    """Return the PySide6.QtWidgets module, or None when Qt cannot load."""
    _qt_prepare_egl_stub()
    try:
        import PySide6.QtWidgets  # noqa: F401
    except Exception:
        return None
    import PySide6.QtWidgets as QtWidgets
    return QtWidgets


def _ensure_offscreen_platform():
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")


_ensure_offscreen_platform()
_qt_prepare_egl_stub()


@pytest.fixture(scope="session")
def qapp():
    """Session-scoped QApplication for headless widget tests."""
    widgets = qt_modules_available()
    if widgets is None:
        pytest.skip("PySide6 is not importable in this environment")
    app = widgets.QApplication.instance() or widgets.QApplication([])
    yield app
