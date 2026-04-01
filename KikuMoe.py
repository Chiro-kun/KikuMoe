import sys
import os
import traceback
from PyQt5.QtWidgets import QApplication
from ui.main_window import ListenMoePlayer


def _write_crash_log(exc: BaseException) -> str:
    local_app_data = os.environ.get("LOCALAPPDATA", "")
    base_dir = os.path.join(local_app_data, "KikuMoe") if local_app_data else os.getcwd()
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
    try:
        app = QApplication(sys.argv)
        window = ListenMoePlayer()
        window.show()
        return app.exec_()
    except Exception as exc:
        log_path = _write_crash_log(exc)
        try:
            print("Startup crash:", exc)
            print("Dettagli in:", log_path)
        except Exception:
            pass
        return 1


if __name__ == '__main__':
    sys.exit(main())
