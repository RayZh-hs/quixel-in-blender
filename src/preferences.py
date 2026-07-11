"""Addon preferences.

The ``AddonPreferences`` panel shown in Blender's Preferences > Add-ons: the
Blender executable path, the asset data directory (whose ``update`` callback
rebuilds the directories + venv), the system Python used to create that venv, and
the cache-management / support buttons.

``bl_idname`` must equal the top-level addon id (:data:`constants.ADDON_ID`), which
is also how the rest of the code looks these preferences up.

Depends on :mod:`.constants` and :mod:`.paths`.
"""

import bpy

from .constants import (
    ADDON_ID,
    DEF_ASSET_DATA_PATH,
    DEF_BLENDER_EXECUTABLE_PATH,
    DEF_SYSTEM_PYTHON,
)
from .paths import (
    get_jsonfile_cache_size,
    get_thumbnail_cache_size,
    get_zipfile_cache_size,
    is_valid_python_path,
    update_asset_data_path,
)


class AssetProcessorPreferences(bpy.types.AddonPreferences):
    """Preferences for the addon"""
    bl_idname = ADDON_ID

    blender_executable_path: bpy.props.StringProperty(
        name="Blender Executable Path",
        description="Path to the Blender executable",
        subtype='FILE_PATH',
        default=DEF_BLENDER_EXECUTABLE_PATH,
    )

    asset_data_path: bpy.props.StringProperty(
        name="Asset Data Path",
        description="Path to save assets data",
        subtype='DIR_PATH',
        default=DEF_ASSET_DATA_PATH,
        update=lambda self, context: update_asset_data_path(self, context)
    )

    system_python: bpy.props.StringProperty(
        name="System Python Path",
        description="Path to the system Python executable",
        subtype='FILE_PATH',
        default=DEF_SYSTEM_PYTHON,
    )

    def draw(self, context):
        layout = self.layout

        layout.prop(self, "blender_executable_path")
        layout.prop(self, "asset_data_path")
        layout.prop(self, "system_python")
        if not is_valid_python_path(self.system_python):
            layout.label(text="Set a valid Python executable path!", icon='ERROR')

        layout.separator()
        row = layout.row()
        row.operator("preferences.update_data_path", icon='FILE_REFRESH')
        row.operator("preferences.setup_env", icon='FILE_REFRESH')

        row = layout.row()
        row.operator("wm.url_open", text="Report a Bug", icon='URL').url = "https://github.com/cgmaterial/fab-to-blender/issues/new"
        row.operator("wm.url_open", text="Support Development", icon='FUND').url = "https://ko-fi.com/cg_material"

        row = layout.row()
        row.operator("filebrowser.clear_thumbnails",
                     text=f"{get_thumbnail_cache_size(context):.2f} MB Thumbnail Cache", icon='TRASH')
        row.operator("filebrowser.clear_jsonfiles",
                     text=f"{get_jsonfile_cache_size(context):.2f} MB JSON Cache", icon='TRASH')
        row.operator("filebrowser.clear_zipfiles",
                     text=f"{get_zipfile_cache_size(context):.2f} MB ZIP file Cache", icon='TRASH')
