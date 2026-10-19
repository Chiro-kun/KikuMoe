import os
import signal
import sys
import traceback
from datetime import datetime

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication

from ui.main_window import ListenMoePlayer

_IS_WIN32 = sys.platform == "win32"
_MAX_CRASH_LOG_SIZE = 512 * 1024  # 512 KB

if not _IS_WIN32 and "QT_QPA_PLATFORM" not in os.environ:
    os.environ["QT_QPA_PLATFORM"] = "wayland;xcb"


def _rotate_crash_log(log_path: str, max_bytes: int = _MAX_CRASH_LOG_SIZE) -> None:
    try:
        if os.path.isfile(log_path) and os.path.getsize(log_path) >= max_bytes:
            backup_path = f"{log_path}.1"
            try:
                os.replace(log_path, backup_path)
            except Exception:
                with open(log_path, "w", encoding="utf-8") as f:
                    f.truncate(0)
    except Exception:
        pass


def _write_crash_log(exc: BaseException) -> str:
    if _IS_WIN32:
        local_app_data = os.environ.get("LOCALAPPDATA", "")
        base_dir = os.path.join(local_app_data, "KikuMoe") if local_app_data else os.getcwd()
    else:
        xdg_data = os.environ.get("XDG_DATA_HOME", "")
        base_dir = (
            os.path.join(xdg_data, "KikuMoe")
            if xdg_data
            else os.path.join(os.path.expanduser("~"), ".local", "share", "KikuMoe")
        )
    try:
        os.makedirs(base_dir, exist_ok=True)
    except Exception:
        pass
    log_path = os.path.join(base_dir, "crash.log")
    _rotate_crash_log(log_path)
    try:
        timestamp = datetime.now().isoformat(sep=" ", timespec="seconds")
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(f"\n=== KikuMoe Crash [{timestamp}] ===\n")
            f.write("".join(traceback.format_exception(type(exc), exc, exc.__traceback__)))
    except Exception:
        pass
    return log_path


def main() -> int:
    if "--debug" in sys.argv:
        sys.argv = [a for a in sys.argv if a != "--debug"]
        from core.logger import set_debug

        set_debug(True)

    try:
        app = QApplication(sys.argv)
        window = ListenMoePlayer()

        def _quit_gracefully(*_: object) -> None:
            try:
                window._cleanup_before_close()
            except Exception:
                pass
            app.exit(0)

        signal.signal(signal.SIGINT, _quit_gracefully)
        if _IS_WIN32:
            # SIGBREAK is Ctrl+Break on Windows; only defined on win32.
            signal.signal(signal.SIGBREAK, _quit_gracefully)  # type: ignore[attr-defined]

        # Qt's C event loop does not yield to Python between iterations, so the
        # signal handler above would never fire without a periodic wakeup.
        _sigint_timer = QTimer()
        _sigint_timer.start(200)
        _sigint_timer.timeout.connect(lambda: None)

        window.show()
        return app.exec()
    except KeyboardInterrupt:
        return 0
    except BaseException as exc:
        log_path = _write_crash_log(exc)
        try:
            print("\n--- CRITICAL STARTUP ERROR ---")
            print(f"Type: {type(exc).__name__}")
            print(f"Error: {exc}")
            print(f"Details written to: {log_path}\n")
        except Exception:
            pass
        return 1


if __name__ == "__main__":
    sys.exit(main())
