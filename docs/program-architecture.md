# Architecture

Quixel in Blender is a Blender **legacy add-on** (not the newer extensions system):
Blender loads the top-level package (folder `quixel-in-blender`) and calls its
`register()` / `unregister()`.

## Top-level layout

```
__init__.py    bl_info + register/unregister — delegates everything to src/
src/           the importable add-on package (runs inside Blender, imports bpy)
scripts/       standalone scripts run as SUBPROCESSES (never imported)
images/        bundled placeholder preview
dev/           developer docs + reference snapshots (not shipped logic)
tests/         placeholder for future tests
```

## The two subprocess boundaries

The single most important thing to understand: **`scripts/` is not imported.** Both
scripts are executed as separate processes, referenced by path via constants in
`src/constants.py` (`FAB_API_SCRIPT`, `ASSET_IMPORTER_SCRIPT`).

1. **`scripts/fab_api.py` runs inside a dedicated venv.**
   It needs `cloudscraper`, `pillow`, `zstandard`, `requests` — packages that are
   not available in Blender's bundled Python. `src/paths.py:setup_env` creates a
   venv (under the user's asset-data path) and pip-installs them. The add-on then
   invokes `<venv>/bin/python scripts/fab_api.py --function <name> ...` for every
   network/image operation (search listings, fetch asset formats, resolve a
   download link, download a file, crop thumbnails). Results are written to JSON
   files in the data dir and read back by the add-on.

2. **`scripts/asset_importer.py` runs via a fresh headless Blender.**
   The "Add To Assets" path launches
   `blender -b --factory-startup -P scripts/asset_importer.py -- <args>` to build
   `.blend` files and mark assets into the asset library without touching the
   user's current session.

Keeping these out-of-process is why relocating them only requires updating the path
constants — there are no imports to fix.

## Module map (`src/`)

Import direction only points downward (no cycles):

```
constants     identity (ADDON_ID), on-disk paths to scripts/images, pref defaults
state         shared mutable runtime globals (queue, cursors, cancel flag,
              preview collection, the visible `assets` dict)
paths         data-dir layout, venv setup, asset-library registration, cache clears
importer      import_to_scene + create_pbr_shader (+ download progress reader)
assets        downloaded-asset JSON store + online search/background-load pipeline
previews      bpy preview-collection lifecycle
preferences   AddonPreferences panel
panels        the Quixel sidebar panel (view only)
operators     every operator (import, search, toggles, cache clear, prefs)
properties    Scene property (un)registration
__init__      class list + register()/unregister() (+ reload support)
```

Two design points worth remembering:

- **Addon id.** `constants.ADDON_ID = __package__.partition(".")[0]` yields the
  top-level folder name (`quixel-in-blender`). It is used both as
  `AddonPreferences.bl_idname` and to look preferences up via
  `context.preferences.addons[ADDON_ID]`. Never use `__name__` for this inside
  `src/*` — there it resolves to `quixel-in-blender.src.<module>`.

- **Shared state.** Values that were module-level `global`s in the original
  single-file add-on now live in `src/state.py`. Rebinding a name goes through the
  module (`state.cancel_loading = True`); in-place container mutation does not
  (`state.asset_queue.put(...)`).

## Data flow — online search

```
Panel search box / operator
        └─> operators.FILEBROWSER_OT_search_assets
                └─> assets.update_assets
                        ├─ subprocess: venv python scripts/fab_api.py --function fetch_assets  → JSON
                        └─ background thread: assets.load_assets_in_background
                                ├─ downloads/crops thumbnails via fab_api.py (thread pool)
                                └─ pushes results onto state.asset_queue
        bpy timer: assets.update_ui_from_queue
                └─ drains queue → state.assets + preview collection → panel redraw
```

## Data flow — import

```
Panel thumbnail button
   ├─ import_asset.import (online): resolve format → resolve download link →
   │     download zip (fab_api.py) → import_to_scene OR asset_importer.py subprocess
   └─ import_downloaded_asset.import (downloaded): import_to_scene OR asset_importer.py
```
