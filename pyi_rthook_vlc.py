import os
import sys

# Runtime hook to help PyInstaller bundles locate VLC runtime and plugins
try:
    base_dir = getattr(sys, "_MEIPASS", None) or os.path.dirname(sys.executable)
    # Add both base_dir and "_internal" (PyInstaller contents directory) to PATH
    internal_dir = os.path.join(base_dir, "_internal")
    new_path_parts = []
    if os.path.isdir(internal_dir):
        new_path_parts.append(internal_dir)
    if os.path.isdir(base_dir):
        new_path_parts.append(base_dir)
    if new_path_parts:
        os.environ["PATH"] = os.pathsep.join(new_path_parts + [os.environ.get("PATH", "")])

    # Point VLC to bundled plugins directory if present
    plugins_candidates = [
        os.path.join(base_dir, "plugins"),
        os.path.join(internal_dir, "plugins"),
    ]
    for p in plugins_candidates:
        if os.path.isdir(p):
            os.environ["VLC_PLUGIN_PATH"] = p
            break
except Exception:
    # Non-fatal if something goes wrong
    pass