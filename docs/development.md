# Development

## Environment setup

```bash
# Clone the repository
git clone https://git.alsogamer.com/chiro/KikuMoe.git
cd KikuMoe

# Create a virtual environment
python -m venv .venv
source .venv/bin/activate      # Linux/macOS
.venv\Scripts\activate         # Windows PowerShell

# Install runtime dependencies
pip install -r requirements.txt

# Run the application
python KikuMoe.py
```

**Build-time dependencies** (not in `requirements.txt`):

```bash
pip install pyinstaller pyinstaller-hooks-contrib
```

---

## Settings system

All settings persist via `QSettings`:

```python
from PyQt5.QtCore import QSettings
from core.constants import ORG_NAME, APP_SETTINGS, KEY_VOLUME

settings = QSettings(ORG_NAME, APP_SETTINGS)

vol = settings.value(KEY_VOLUME, 80, type=int)   # read with default
settings.setValue(KEY_VOLUME, 75)                 # write
```

- **Windows:** `HKEY_CURRENT_USER\Software\KikuMoe\ListenMoePlayer`
- **Linux/macOS:** INI file at a path determined by Qt

Always use the constants from `core/constants.py`. Never use string literals as keys.

---

## Internationalization (i18n)

To add or modify strings:

1. Open [core/i18n.py](../core/i18n.py).
2. Find the translations dictionary.
3. Add/update the key in both the `"it"` and `"en"` sections.

To add a new language (e.g. French):

1. Add a `"fr"` section in `core/i18n.py` with all keys translated (use `"en"` as the base).
2. In [ui/settings_dialog.py](../ui/settings_dialog.py), add `"fr"` to the language selector list.

Strings are accessed everywhere via `self._i18n.t("key")`. A runtime language switch calls `retranslateUi()` without restarting.

---

## Versioning

The version is defined in `version.yml` at the repository root:

```yaml
version: 1.9.0
```

To release a new version:

1. Update `version.yml`.
2. Update `packaging/windows/version_info.txt` (`filevers` and `FileVersion` fields).
3. Update the output name in `kikumoe.spec` (`name='KikuMoe-X.Y.Z'`) and in `build.ps1`.
4. Create the tag: `git tag vX.Y.Z`.

---

## Code conventions

- **Style:** PEP 8, 4-space indentation. No formatter is enforced.
- **Imports:** absolute from the root (`from core.constants import ...`), not relative.
- **Logging:** use `get_logger(__name__)` instead of `print()` for debug output.
- **UI thread safety:** any UI update from a non-main thread must go through a Qt signal. Never call Qt methods directly from secondary threads.
- **UI strings:** always use `self._i18n.t("key")`. Never hardcode user-visible strings.
- **Settings keys:** always use the constants from `core/constants.py`. Never use string literals.
