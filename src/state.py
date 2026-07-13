"""Shared mutable runtime state.

In the original single-file addon these were module-level globals mutated from
many functions via ``global``. Split across modules, ``global`` no longer reaches
them, so they live here and every writer refers to them as ``state.<name> = ...``.

Rule of thumb used throughout the codebase:

* Rebinding a name (``state.cancel_loading = True``, ``state.loading_thread = t``)
  **must** go through this module.
* Mutating a container in place (``state.cursors["next_cursor"] = ...``,
  ``state.manifest.append(...)``, ``state.pending_downloads.pop(0)``) can be done on
  the object directly.
"""

# The current background loading thread (or None when idle).
loading_thread = None

# Pagination cursors for the online search ("0" == first page).
cursors = {"curr_cursor": "0", "next_cursor": "0"}

# Cooperative-cancellation flag for the background loader.
cancel_loading = False

# Accumulated placeholder-manifest entries for the current online session. A fresh
# search clears it; "Load More" appends. The whole list is rebuilt into
# placeholders.blend on each background load. See assets.load_assets_in_background.
manifest = []

# Drag-download jobs queued by the depsgraph handler when a placeholder is dropped
# into the scene, drained by a main-thread timer. See handlers. Each item is a dict:
# {"kind", "dummy_name", "uid", "asset_type", "size", "target_object"}.
pending_downloads = []
