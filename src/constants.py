"""Static configuration shared across the addon.

Holds the addon identifier, on-disk paths to the addon's own files (the
standalone subprocess scripts and the placeholder preview image) and the default
values used by the preferences. Nothing here imports other addon modules, so this
is safe to import from anywhere.

Two things deserve care:

* ``ADDON_ID`` must equal the *top-level* package name (the folder Blender loads,
  e.g. ``quixel-in-blender``). It is used both as ``AddonPreferences.bl_idname``
  and to look preferences up via ``context.preferences.addons[ADDON_ID]``. Inside
  this subpackage ``__package__`` is ``quixel-in-blender.src``, so we take the part
  before the first dot.
* ``ADDON_DIR`` is the addon root, one level above this ``src/`` package. The
  script/image paths are derived from it because ``fab_api.py`` and
  ``asset_importer.py`` are executed as external processes *by path* — they are
  never imported.
"""

import os
import platform
import subprocess

import bpy

# --- Identity -------------------------------------------------------------
# Top-level package / addon id (folder name), e.g. "quixel-in-blender".
ADDON_ID = __package__.partition(".")[0]

# --- Directories and bundled files ---------------------------------------
# Addon root = parent of this src/ package.
ADDON_DIR = os.path.dirname(os.path.dirname(__file__))

# Standalone scripts run as subprocesses (NOT imported):
#   fab_api.py runs inside the addon's venv (needs cloudscraper/PIL/zstandard);
#   asset_importer.py runs via `blender -b --factory-startup -P`.
SCRIPTS_DIR = os.path.join(ADDON_DIR, "scripts")
FAB_API_SCRIPT = os.path.join(SCRIPTS_DIR, "fab_api.py")
ASSET_IMPORTER_SCRIPT = os.path.join(SCRIPTS_DIR, "asset_importer.py")

# Placeholder thumbnail shown before a real preview is downloaded.
PREVIEW_IMG = os.path.join(ADDON_DIR, "images", "preview.svg")

# --- Asset library --------------------------------------------------------
# Display name of the asset library this addon registers in Blender.
ASSET_LIB_NAME = "Quixel Assets"

# --- Preference defaults --------------------------------------------------
# Path to the currently running Blender executable.
DEF_BLENDER_EXECUTABLE_PATH = bpy.app.binary_path

# Default location under which the addon stores its downloaded data.
DEF_ASSET_DATA_PATH = os.path.join(
    os.getenv("USERPROFILE" if platform.system() == "Windows" else "HOME"),
    "Documents",
)

# Best-effort autodetection of a system Python (used to build the venv).
try:
    DEF_SYSTEM_PYTHON = subprocess.check_output(
        ["where" if platform.system() == "Windows" else "which", "python3"]
    ).strip().decode("utf-8")
except Exception:
    DEF_SYSTEM_PYTHON = ""
