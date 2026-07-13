"""Addon package: class registry and (un)registration.

The root ``__init__.py`` (which carries ``bl_info``) delegates ``register()`` /
``unregister()`` here. This module owns the ordered list of Blender classes and the
register/unregister lifecycle: scene properties, the ``qib_asset`` placeholder
properties, the drag-download handlers, the version-gated Asset Shelf, and the
one-time runtime initialisation (directories, venv).

Submodules are reloaded in dependency order when Blender re-runs the addon
("Reload Scripts") so that dependents rebind to freshly reloaded dependencies.
"""

# --- Reload support (dependency order: bases first) -----------------------
if "bpy" in locals():
    import importlib
    for _m in (constants, compat, state, catalog, paths, importer, assets, dummy,
               handlers, preferences, panels, operators, properties):
        importlib.reload(_m)
else:
    from . import (constants, compat, state, catalog, paths, importer, assets, dummy,
                   handlers, preferences, panels, operators, properties)

import bpy

from .compat import register_gated
from .dummy import QIBAssetInfo, register_dummy_properties, unregister_dummy_properties
from .handlers import register_handlers, unregister_handlers
from .preferences import AssetProcessorPreferences
from .panels import ASSETBROWSER_PT_quixel_search, FILEBROWSER_PT_assets, SHELF_CLASSES
from .operators import (
    FILEBROWSER_OT_clear_jsonfiles,
    FILEBROWSER_OT_clear_thumbnails,
    FILEBROWSER_OT_clear_zipfiles,
    FILEBROWSER_OT_load_more,
    FILEBROWSER_OT_search_assets,
    FILEBROWSER_OT_set_asset_type,
    FILEBROWSER_OT_set_import_size,
    FILEBROWSER_OT_set_import_type,
    IMPORT_ASSET_OT_import_asset,
    PREFERENCES_OT_setup_env,
    PREFERENCES_OT_update_data_path,
    QIB_OT_open_asset_browser,
)
from .properties import register_properties, unregister_properties
from .paths import fix_asset_paths, initialize_paths, setup_env


# QIBAssetInfo must be registered before register_dummy_properties() assigns the
# PointerProperty onto Object/Material/World, so it comes first.
classes = [
    QIBAssetInfo,
    FILEBROWSER_PT_assets,
    ASSETBROWSER_PT_quixel_search,
    FILEBROWSER_OT_load_more,
    IMPORT_ASSET_OT_import_asset,
    QIB_OT_open_asset_browser,
    FILEBROWSER_OT_search_assets,
    FILEBROWSER_OT_clear_thumbnails,
    FILEBROWSER_OT_clear_jsonfiles,
    FILEBROWSER_OT_clear_zipfiles,
    PREFERENCES_OT_update_data_path,
    PREFERENCES_OT_setup_env,
    FILEBROWSER_OT_set_asset_type,
    FILEBROWSER_OT_set_import_type,
    FILEBROWSER_OT_set_import_size,
    AssetProcessorPreferences,
]

# Populated by register(); the exact set of gated classes that registered, so
# unregister() removes precisely those.
_registered_shelves = []


def register():
    global _registered_shelves
    for cls in classes:
        bpy.utils.register_class(cls)
    register_dummy_properties()
    register_properties()
    _registered_shelves = register_gated(SHELF_CLASSES)
    register_handlers()
    initialize_paths(bpy.context)
    setup_env(bpy.context)
    fix_asset_paths(bpy.context)


def unregister():
    unregister_handlers()
    for cls in reversed(_registered_shelves):
        bpy.utils.unregister_class(cls)
    _registered_shelves.clear()
    unregister_dummy_properties()
    unregister_properties()
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)
