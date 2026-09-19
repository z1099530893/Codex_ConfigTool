"""Redirect every path the application persists to, for measurement runs.

Both server scripts under this directory launch the *real* application window
so ``proto_restore_flash.py`` can measure it.  A real window writes real state:
``load_path`` creates a template config on first use and ``save_settings``
rewrites ``settings.json``.  Neither may happen to the user's machine, so both
paths are rebound to a throwaway directory before the window is built.

``codex_config_tool`` keeps ``SETTINGS_DIR`` and ``SETTINGS_FILE`` as module
globals and reads them inside ``load_settings``/``save_settings``/
``save_setting_value``, so rebinding the globals is sufficient.
"""

from __future__ import annotations

import shutil
import tempfile
from pathlib import Path


def isolate(prefix: str = "codex-measure-") -> tuple[Path, Path]:
    """Point all persisted state at a temp directory.

    Returns ``(root, config_dir)``.  Call ``cleanup(root)`` when done.

    The path is resolved before it is returned: ``tempfile.mkdtemp`` hands back
    the 8.3 short form on this machine (``C:\\Users\\ADMINI~1\\...``) while the
    application canonicalizes every path it is given with ``Path.resolve()``.
    A harness that compares the two would then see a mismatch that looks like a
    bug in the app.  Returning the long form removes the trap for every caller.
    """
    import codex_config_tool as core

    root = Path(tempfile.mkdtemp(prefix=prefix)).resolve()
    core.SETTINGS_DIR = root / "settings"
    core.SETTINGS_FILE = core.SETTINGS_DIR / "settings.json"
    return root, root / ".codex"


def cleanup(root: Path) -> None:
    shutil.rmtree(root, ignore_errors=True)
