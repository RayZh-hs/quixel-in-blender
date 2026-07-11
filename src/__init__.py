"""Addon package: class registry and (un)registration.

The root ``__init__.py`` (which carries ``bl_info``) delegates ``register()`` /
``unregister()`` here. This module owns the ordered list of Blender classes and the
register/unregister lifecycle, including scene-property registration and the
one-time runtime initialisation (directories, venv, preview collection).

Submodules are reloaded in dependency order when Blender re-runs the addon
("Reload Scripts") so that dependents rebind to freshly reloaded dependencies.
"""

# --- Reload support (dependency order: bases first) -----------------------
if "bpy" in locals():
    import importlib
    for _m in (constants, state, paths, importer, assets, previews,
               preferences, panels, operators, properties):
        importlib.reload(_m)
else:
    from . import (constants, state, paths, importer, assets, previews,
                   preferences, panels, operators, properties)

import bpy

from .preferences import AssetProcessorPreferences
from .panels import FILEBROWSER_PT_assets
from .operators import (
    FILEBROWSER_OT_clear_jsonfiles,
    FILEBROWSER_OT_clear_thumbnails,
    FILEBROWSER_OT_clear_zipfiles,
    FILEBROWSER_OT_load_more,
    FILEBROWSER_OT_search_assets,
    FILEBROWSER_OT_set_asset_mode,
    FILEBROWSER_OT_set_asset_type,
    FILEBROWSER_OT_set_downloaded_asset_type,
    FILEBROWSER_OT_set_downloaded_import_method,
    FILEBROWSER_OT_set_downloaded_import_size,
    FILEBROWSER_OT_set_import_size,
    FILEBROWSER_OT_set_import_type,
    IMPORT_ASSET_OT_import_asset,
    IMPORT_DOWNLOADED_ASSET_OT_import,
    PREFERENCES_OT_setup_env,
    PREFERENCES_OT_update_data_path,
)
from .properties import register_properties, unregister_properties
from .paths import fix_asset_paths, initialize_paths, setup_env
from .previews import cleanup_preview_collection, initialize_preview_collection
from . import state


classes = [
    FILEBROWSER_PT_assets,
    FILEBROWSER_OT_load_more,
    IMPORT_ASSET_OT_import_asset,
    FILEBROWSER_OT_search_assets,
    FILEBROWSER_OT_clear_thumbnails,
    FILEBROWSER_OT_clear_jsonfiles,
    FILEBROWSER_OT_clear_zipfiles,
    PREFERENCES_OT_update_data_path,
    PREFERENCES_OT_setup_env,
    FILEBROWSER_OT_set_asset_mode,
    FILEBROWSER_OT_set_asset_type,
    FILEBROWSER_OT_set_import_type,
    FILEBROWSER_OT_set_import_size,
    FILEBROWSER_OT_set_downloaded_asset_type,
    FILEBROWSER_OT_set_downloaded_import_size,
    FILEBROWSER_OT_set_downloaded_import_method,
    IMPORT_DOWNLOADED_ASSET_OT_import,
    AssetProcessorPreferences,
]


def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    register_properties()
    state.assets = {}
    initialize_paths(bpy.context)
    setup_env(bpy.context)
    initialize_preview_collection(bpy.context)
    fix_asset_paths(bpy.context)


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
    unregister_properties()
    cleanup_preview_collection()
