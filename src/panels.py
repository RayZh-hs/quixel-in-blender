"""The Quixel sidebar panel (View3D > Sidebar > Quixel).

Since browsing now happens in Blender's native Asset Browser (online results appear
there as placeholder assets; dragging one downloads it), this panel is purely a set of
*actions*: configure the online search, set the import defaults baked into
placeholders, open the Asset Browser, and manage caches.

It triggers work by invoking operators through their ``bl_idname`` strings, so it does
not import :mod:`.operators`.
"""

import bpy

from .constants import ASSET_LIB_NAME
from .compat import requires_blender_version


def draw_search(layout, scene):
    """Online-search controls: asset-type toggles, query, sort, Search / Load More."""
    box = layout.box()
    box.label(text="Search", icon='VIEWZOOM')
    row = box.row(align=True)
    row.operator("filebrowser.set_asset_type", text="3D Model",
                 depress=scene.asset_type == '3d-model').asset_type = '3d-model'
    row.operator("filebrowser.set_asset_type", text="Material",
                 depress=scene.asset_type == 'material').asset_type = 'material'
    row.operator("filebrowser.set_asset_type", text="Decal",
                 depress=scene.asset_type == 'decal').asset_type = 'decal'
    row = box.row(align=True)
    row.prop(scene, "asset_search", text="", icon='VIEWZOOM')
    row.prop(scene, "sort_method", text="")
    box.operator("filebrowser.search_assets", text="Search / Refresh Assets", icon='FILE_REFRESH')
    box.operator("filebrowser.load_more", text="Load More", icon='PLUS')


def draw_import_settings(layout, scene):
    """Import defaults baked into placeholders and used when an asset is dragged in."""
    box = layout.box()
    box.label(text="Import Settings", icon='IMPORT')
    row = box.row(align=True)
    row.operator("filebrowser.set_import_size", text="raw",
                 depress=scene.import_size == '0').import_size = '0'
    row.operator("filebrowser.set_import_size", text="high",
                 depress=scene.import_size == '1').import_size = '1'
    row.operator("filebrowser.set_import_size", text="mid",
                 depress=scene.import_size == '2').import_size = '2'
    row.operator("filebrowser.set_import_size", text="low",
                 depress=scene.import_size == '3').import_size = '3'
    row = box.row(align=True)
    row.operator("filebrowser.set_import_type", text="Import To Scene",
                 depress=scene.import_type == 'import_to_scene').import_type = 'import_to_scene'
    row.operator("filebrowser.set_import_type", text="Add To Assets",
                 depress=scene.import_type == 'add_to_asset_library').import_type = 'add_to_asset_library'


def draw_cache_actions(layout):
    """Cache-clearing buttons."""
    row = layout.row(align=True)
    row.operator("filebrowser.clear_thumbnails", text="Thumbnails", icon='TRASH')
    row.operator("filebrowser.clear_jsonfiles", text="JSON", icon='TRASH')
    row.operator("filebrowser.clear_zipfiles", text="ZIPs", icon='TRASH')


class FILEBROWSER_PT_assets(bpy.types.Panel):
    bl_label = "Quixel Assets"
    bl_idname = "FILEBROWSER_PT_assets"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Quixel'

    def draw(self, context):
        scene = context.scene
        layout = self.layout

        draw_search(layout, scene)
        draw_import_settings(layout, scene)

        # --- Actions -------------------------------------------------------
        box = layout.box()
        box.label(text="Actions", icon='TOOL_SETTINGS')
        box.operator("quixel.open_asset_browser", text=f"Open {ASSET_LIB_NAME}", icon='ASSET_MANAGER')
        draw_cache_actions(box)


class ASSETBROWSER_PT_quixel_search(bpy.types.Panel):
    """Online Quixel search, shown in the Asset Browser's left region below the library
    dropdown and catalog tree, so results can be searched from the same window they
    appear in. The Browser's own search box only filters already-loaded assets (Blender
    gives addons no hook to intercept it)."""
    bl_label = "Quixel Search"
    bl_idname = "ASSETBROWSER_PT_quixel_search"
    bl_space_type = 'FILE_BROWSER'
    bl_region_type = 'TOOLS'
    bl_order = 100  # after the native catalog tree

    @classmethod
    def poll(cls, context):
        return context.area is not None and context.area.ui_type == 'ASSETS'

    def draw(self, context):
        scene = context.scene
        layout = self.layout
        draw_search(layout, scene)
        draw_import_settings(layout, scene)
        draw_cache_actions(layout.box())


# --- Optional 5.2+ quick-access Asset Shelf in the 3D viewport ---------------
# The class definition itself is guarded: AssetShelf must exist before the version
# gate is even consulted. register_gated() then skips it on Blenders below 5.2.
if hasattr(bpy.types, "AssetShelf"):

    @requires_blender_version(min=(5, 2, 0))
    class QIB_AST_shelf(bpy.types.AssetShelf):
        bl_space_type = 'VIEW_3D'
        bl_idname = "QIB_AST_shelf"

        @classmethod
        def poll(cls, context):
            return context.mode == 'OBJECT'

        @classmethod
        def asset_poll(cls, asset):
            return asset.id_type in {'MATERIAL', 'OBJECT'}

    SHELF_CLASSES = [QIB_AST_shelf]
else:
    SHELF_CLASSES = []
