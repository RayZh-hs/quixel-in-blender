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

## The three subprocess boundaries

The single most important thing to understand: **`scripts/` is not imported.** All
three scripts are executed as separate processes, referenced by path via constants in
`src/constants.py` (`FAB_API_SCRIPT`, `ASSET_IMPORTER_SCRIPT`, `PLACEHOLDER_BUILDER_SCRIPT`).

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
   per-asset `.blend` files and mark assets into the asset library.

3. **`scripts/placeholder_builder.py` runs via a fresh headless Blender.**
   Online search results become lightweight "dummy" marked assets in one shared
   `placeholders.blend`, so they appear in Blender's native Asset Browser with the
   Fab category tree as the left nav. Launched with `bpy.app.binary_path` (the
   running Blender) so the saved `.blend` version matches the session that reads it.
   Because `scripts/` is never imported, its catalog/token helpers are duplicated
   from `src/catalog.py` / `src/dummy.py` — keep the copies in sync.

Keeping these out-of-process is why relocating them only requires updating the path
constants — there are no imports to fix.

## Module map (`src/`)

Import direction only points downward (no cycles):

```
constants     identity (ADDON_ID), on-disk paths to scripts/images, pref defaults
compat        Blender-version gating (requires_blender_version, register_gated)
state         shared mutable runtime globals (cursors, cancel flag, manifest,
              pending drag-download jobs)
catalog       Fab category -> blender_assets.cats.txt path mapping (canonical copy;
              mirrored inside scripts/placeholder_builder.py)
paths         data-dir layout, venv setup, asset-library registration, cache clears
importer      import_to_scene + create_pbr_shader (+ download progress reader)
assets        downloaded-asset store + import core (download_and_build_asset) +
              online search -> placeholder-manifest pipeline
dummy         qib_asset PropertyGroup (placeholder identity) + pointer (un)registration
handlers      depsgraph/undo drag-download: dropped placeholder -> real download
preferences   AddonPreferences panel
panels        the Quixel sidebar panel (actions only) + gated Asset Shelf (5.2+)
operators     import / search / toggles / open-asset-browser / cache clear / prefs
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

## Data flow — online search → native Asset Browser

```
Sidebar search button / set_asset_type
        └─> operators.FILEBROWSER_OT_search_assets  (clears state.manifest)
                └─> assets.update_assets
                        ├─ subprocess: venv python scripts/fab_api.py --function fetch_assets → JSON
                        └─ background thread: assets.load_assets_in_background
                                ├─ downloads/crops thumbnails via fab_api.py (thread pool)
                                ├─ accumulates entries into state.manifest
                                └─ assets.build_placeholders: blender -b -P placeholder_builder.py
                                         → writes shared placeholders.blend (dummy marked assets)
        bpy timer: assets._schedule_refresh → asset.library_refresh()
                └─ dummies appear in the native Asset Browser under the Fab catalog tree
```

## Data flow — drag-download (the main import path)

```
User drags a placeholder from the Asset Browser into the scene
        └─> handlers.on_depsgraph_pre  (depsgraph_update_pre)
                ├─ detects the dropped dummy (qib_asset.is_dummy or QIB: token)
                ├─ _claim() it (clear flag + token so it's handled once)
                └─ enqueue job → state.pending_downloads
        bpy timer: handlers.drain_pending  (one job per tick)
                ├─ remove the dummy datablock
                └─ assets.download_and_build_asset(..., import_to_scene)
                        resolve format → resolve link → download zip (fab_api.py) →
                        importer.import_to_scene (FBX / PBR material)
undo/redo: handlers.on_undo_redo strips any lingering dummy
```

## Data flow — direct import (sidebar fallback / Add To Assets)

```
import_asset.import  → assets.download_and_build_asset
   ├─ import_to_scene:        importer.import_to_scene
   └─ add_to_asset_library:   blender -b -P scripts/asset_importer.py (per-asset .blend)
```
