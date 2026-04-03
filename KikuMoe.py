import os
import signal
import sys
import traceback

from PyQt5.QtCore import QTimer
from PyQt5.QtWidgets import QApplication

from ui.main_window import ListenMoePlayer

_IS_WIN32 = sys.platform == "win32"


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
    try:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write("\n=== KikuMoe Crash ===\n")
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
        return app.exec_()
    except KeyboardInterrupt:
        return 0
    except Exception as exc:
        log_path = _write_crash_log(exc)
        try:
            print("Startup crash:", exc)
            print("Dettagli in:", log_path)
        except Exception:
            pass
        return 1


if __name__ == "__main__":
    sys.exit(main())
