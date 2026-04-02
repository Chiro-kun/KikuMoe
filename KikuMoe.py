import sys
import os
import traceback
from PyQt6.QtWidgets import QApplication
from ui.main_window import ListenMoePlayer

_IS_WIN32 = sys.platform == "win32"

if not _IS_WIN32 and "QT_QPA_PLATFORM" not in os.environ:
    os.environ["QT_QPA_PLATFORM"] = "wayland;xcb"


def _write_crash_log(exc: BaseException) -> str:
    if _IS_WIN32:
        local_app_data = os.environ.get("LOCALAPPDATA", "")
        base_dir = os.path.join(local_app_data, "KikuMoe") if local_app_data else os.getcwd()
    else:
        xdg_data = os.environ.get("XDG_DATA_HOME", "")
        base_dir = os.path.join(xdg_data, "KikuMoe") if xdg_data else os.path.join(os.path.expanduser("~"), ".local", "share", "KikuMoe")
    try:
        os.makedirs(base_dir, exist_ok=True)
    except Exception:
        pass
    log_path = os.path.join(base_dir, "crash.log")
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write("\n=== KikuMoe Crash ===\n")
            f.write("".join(traceback.format_exception(type(exc), exc, exc.__traceback__)))
    except Exception:
        pass
    return log_path


def main() -> int:
    if '--debug' in sys.argv:
        sys.argv = [a for a in sys.argv if a != '--debug']
        from core.logger import set_debug
        set_debug(True)

    try:
        app = QApplication(sys.argv)
        window = ListenMoePlayer()
        window.show()
        return app.exec()
    except BaseException as exc:
        log_path = _write_crash_log(exc)
        try:
            print(f"\n--- CRITICAL STARTUP ERROR ---")
            print(f"Type: {type(exc).__name__}")
            print(f"Error: {exc}")
            print(f"Details written to: {log_path}\n")
        except Exception:
            pass
        return 1


if __name__ == '__main__':
    sys.exit(main())
