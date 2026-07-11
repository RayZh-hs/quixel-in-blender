"""The Quixel sidebar panel (View3D > Sidebar > Quixel).

Draws the whole UI: the Online/Downloaded mode toggle, the asset-type / import-size
/ import-method rows, the search box, and the responsive thumbnail grid. It is
purely a view — it reads shared state (:data:`state.assets`,
:data:`state.preview_collection`) and the downloaded-asset store, and triggers work
by invoking operators through their ``bl_idname`` strings (so no import of
:mod:`.operators` is needed).

Depends on :mod:`.state`, :mod:`.paths` and :mod:`.assets`.
"""

import os

import bpy

from . import state
from .paths import get_asset_paths
from .assets import filter_downloaded_assets, load_downloaded_assets


class FILEBROWSER_PT_assets(bpy.types.Panel):
    bl_label = "Quixel Assets"
    bl_idname = "FILEBROWSER_PT_assets"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Quixel'

    def draw(self, context):
        layout = self.layout
        layout.alignment = "CENTER"
        row = layout.row(align=True)
        row.operator("filebrowser.set_asset_mode", text="Online",
                     depress=context.scene.asset_mode == 'online').asset_mode = 'online'
        row.operator("filebrowser.set_asset_mode", text="Downloaded",
                     depress=context.scene.asset_mode == 'downloaded').asset_mode = 'downloaded'
        paths = get_asset_paths(context)

        if context.scene.asset_mode == 'online':
            box = layout.box()
            row = box.row(align=True)
            row.operator("filebrowser.set_asset_type", text="3D Model",
                         depress=context.scene.asset_type == '3d-model').asset_type = '3d-model'
            row.operator("filebrowser.set_asset_type", text="Material",
                         depress=context.scene.asset_type == 'material').asset_type = 'material'
            row.operator("filebrowser.set_asset_type", text="Decal",
                         depress=context.scene.asset_type == 'decal').asset_type = 'decal'
            row = box.row(align=True)
            row.operator("filebrowser.set_import_size", text="raw",
                         depress=context.scene.import_size == '0').import_size = '0'
            row.operator("filebrowser.set_import_size", text="high",
                         depress=context.scene.import_size == '1').import_size = '1'
            row.operator("filebrowser.set_import_size", text="mid",
                         depress=context.scene.import_size == '2').import_size = '2'
            row.operator("filebrowser.set_import_size", text="low",
                         depress=context.scene.import_size == '3').import_size = '3'
            row = box.row(align=True)
            row.operator("filebrowser.set_import_type", text="Import To Scene",
                         depress=context.scene.import_type == 'import_to_scene').import_type = 'import_to_scene'
            row.operator("filebrowser.set_import_type", text="Add To Assets",
                         depress=context.scene.import_type == 'add_to_asset_library').import_type = 'add_to_asset_library'
            row = box.row(align=True)
            row.prop(context.scene, "asset_search", text="", icon='VIEWZOOM')
            row.prop(context.scene, "sort_method", text="")
            # row.operator("filebrowser.search_assets", text="", icon='VIEWZOOM')
            if state.assets:
                if state.cancel_loading:
                    print("Loading cancelled.")
                    layout.label(text="Loading Cancelled.")
                    return
                if len(state.assets) == 0:
                    layout.label(text="No assets available. Try searching or refreshing.")
                else:
                    row = box.row(align=True)
                    min_width = 120
                    columns_count = max(1, min(int(context.region.width / min_width), len(state.assets)))
                    column_list = [row.column(align=True) for _ in range(columns_count)]
                    for i, (uid, asset_data) in enumerate(state.assets.items()):
                        col = column_list[i % columns_count]
                        asset_box = col.box()
                        asset_box.scale_x = 1.0
                        asset_box.scale_y = 1.0
                        preview = asset_data["preview"]
                        img_path = asset_data["img_path"]
                        asset_name = asset_data["asset_name"]
                        if preview:
                            asset_box.template_icon(preview.icon_id, scale=5)
                        import_btn = asset_box.operator("import_asset.import", text=asset_name, icon="IMPORT")
                        import_btn.asset_name = asset_name
                        import_btn.uid = uid
                        import_btn.img_path = img_path if img_path else "No Image"
            else:
                layout.label(text="Loading assets...")
            row = box.row(align=True)
            row.operator("filebrowser.load_more", text="Load More")

        elif context.scene.asset_mode == 'downloaded':
            box = layout.box()
            downloaded_assets = load_downloaded_assets(context)
            asset_type = context.scene.downloaded_asset_type
            import_size = context.scene.downloaded_import_size
            filtered_assets = filter_downloaded_assets(context, downloaded_assets, asset_type, import_size)
            row = box.row(align=True)
            row.operator("filebrowser.set_downloaded_asset_type", text="3D Model",
                         depress=asset_type == '3d-model').asset_type = '3d-model'
            row.operator("filebrowser.set_downloaded_asset_type", text="Material",
                         depress=asset_type == 'material').asset_type = 'material'
            row.operator("filebrowser.set_downloaded_asset_type", text="Decal",
                         depress=asset_type == 'decal').asset_type = 'decal'
            row = box.row(align=True)
            row.operator("filebrowser.set_downloaded_import_size", text="raw",
                         depress=import_size == '0').import_size = '0'
            row.operator("filebrowser.set_downloaded_import_size", text="high",
                         depress=import_size == '1').import_size = '1'
            row.operator("filebrowser.set_downloaded_import_size", text="mid",
                         depress=import_size == '2').import_size = '2'
            row.operator("filebrowser.set_downloaded_import_size", text="low",
                         depress=import_size == '3').import_size = '3'
            row = box.row(align=True)
            row.operator("filebrowser.set_downloaded_import_method", text="Import To Scene",
                         depress=context.scene.downloaded_import_method == 'import_to_scene').import_method = 'import_to_scene'
            row.operator("filebrowser.set_downloaded_import_method", text="Add To Assets",
                         depress=context.scene.downloaded_import_method == 'add_to_asset_library').import_method = 'add_to_asset_library'
            if filtered_assets:
                row = box.row(align=True)
                min_width = 120
                columns_count = max(1, min(int(context.region.width / min_width), len(filtered_assets)))
                column_list = [row.column(align=True) for _ in range(columns_count)]
                for i, (uid, asset_data) in enumerate(filtered_assets.items()):
                    col = column_list[i % columns_count]
                    asset_box = col.box()
                    asset_box.scale_x = 1.0
                    asset_box.scale_y = 1.0
                    thumbnail_path = asset_data["thumbnail_image"]
                    if os.path.exists(thumbnail_path):
                        preview = state.preview_collection.get(uid)
                        if not preview:
                            state.preview_collection.load(uid, thumbnail_path, 'IMAGE')
                        preview = state.preview_collection[uid]
                        asset_box.template_icon(preview.icon_id, scale=5)
                    import_btn = asset_box.operator("import_downloaded_asset.import", text=asset_data["asset_name"],
                                                    icon="IMPORT")
                    import_btn.asset_uid = uid
                    import_btn.asset_name = os.path.basename(asset_data["asset_path"])
                    import_btn.asset_type = asset_data["asset_type"]
                    import_btn.asset_path = asset_data["asset_path"]
                    import_btn.thumbnail_path = thumbnail_path
                    import_btn.import_method = context.scene.downloaded_import_method
            else:
                box.label(text="No downloaded assets found.")
