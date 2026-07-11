"""Shared mutable runtime state.

In the original single-file addon these were module-level globals mutated from
many functions via ``global``. Split across modules, ``global`` no longer reaches
them, so they live here and every writer refers to them as ``state.<name> = ...``.

Rule of thumb used throughout the codebase:

* Rebinding a name (``state.cancel_loading = True``, ``state.loading_thread = t``,
  ``state.preview_collection = pc``) **must** go through this module.
* Mutating a container in place (``state.asset_queue.put(...)``,
  ``state.cursors["next_cursor"] = ...``, ``state.assets[uid] = ...``) can be done
  on the object directly.
"""

import queue

# Background producer/consumer queue for streaming search results into the UI.
asset_queue = queue.Queue()

# The current background loading thread (or None when idle).
loading_thread = None

# Pagination cursors for the online search ("0" == first page).
cursors = {"curr_cursor": "0", "next_cursor": "0"}

# Blender preview collection holding thumbnail icons (created at register time).
preview_collection = None

# Cooperative-cancellation flag for the background loader.
cancel_loading = False

# UID -> {"preview", "img_path", "asset_name"} for assets currently shown in the
# online panel. Written by the background loader, read/cleared by the UI.
assets = {}
