"""All addon operators.

Grouped here: the online import operator (kept as a thin wrapper / fallback around
:func:`assets.download_and_build_asset`), the search / load-more actions that drive the
online pipeline, the search-parameter toggles the sidebar writes, the "open asset
browser" convenience, the cache-clearing operators, and the two preference operators.

Shared runtime state (threads, cancel flag, cursors, manifest) is mutated through
:mod:`.state`.

Depends on :mod:`.constants`, :mod:`.state`, :mod:`.paths` and :mod:`.assets`.
"""

import bpy

from . import state
from .constants import ADDON_ID, ASSET_LIB_NAME
from .paths import (
    clear_jsonfile_cache,
    clear_thumbnail_cache,
    clear_zipfile_cache,
    setup_env,
    update_asset_data_path,
)
from .assets import download_and_build_asset, update_assets


class IMPORT_ASSET_OT_import_asset(bpy.types.Operator):
    """Download and import an online asset directly (fallback to dragging from the
    Asset Browser)."""
    bl_idname = "import_asset.import"
    bl_label = "Import Asset"
    asset_name: bpy.props.StringProperty()
    uid: bpy.props.StringProperty()
    img_path: bpy.props.StringProperty()

    def execute(self, context):
        context.window.cursor_set('WAIT')
        print(f"Importing Asset: {self.asset_name} (UID: {self.uid})")
        asset_type = str(context.scene.asset_type).strip()
        size = int(context.scene.import_size.strip())
        status, message = download_and_build_asset(
            context, self.uid, asset_type, size, context.scene.import_type,
            display_name=self.asset_name, img_path=self.img_path if self.img_path else None)
        context.window.cursor_set('DEFAULT')
        if status != 0:
            self.report({'ERROR'}, message)
            return {'CANCELLED'}
        self.report({'INFO'}, message)
        return {'FINISHED'}


class QIB_OT_open_asset_browser(bpy.types.Operator):
    """Split the current editor and show the Quixel library in an Asset Browser on the
    left, leaving the existing viewport (and its Quixel sidebar) in place on the right."""
    bl_idname = "quixel.open_asset_browser"
    bl_label = "Open Quixel Asset Browser"

    @staticmethod
    def _find_asset_browser():
        """Return ``(window, area)`` of the first open Quixel Asset Browser, or
        ``(None, None)``. Searches every window, not just the active screen."""
        for win in bpy.context.window_manager.windows:
            for a in win.screen.areas:
                if a.type == 'FILE_BROWSER' and a.ui_type == 'ASSETS':
                    return win, a
        return None, None

    def execute(self, context):
        win, area = self._find_asset_browser()
        if area is None:
            win = context.window
            # Split the biggest editor vertically and make the LEFT half the browser,
            # so the original viewport (and the N-panel Quixel sidebar) survive on the
            # right. Splitting keeps everything inside the current window/workspace.
            target = max(win.screen.areas, key=lambda a: a.width * a.height)
            before = set(win.screen.areas)
            region = next((r for r in target.regions if r.type == 'WINDOW'), None)
            with context.temp_override(window=win, area=target, region=region):
                bpy.ops.screen.area_split(direction='VERTICAL', factor=0.35)
            new_areas = [a for a in win.screen.areas if a not in before]
            if not new_areas:
                self.report({'ERROR'}, "Could not split the editor for the Asset Browser.")
                return {'CANCELLED'}
            # area_split leaves `target` as one half and adds the other; the browser
            # goes in whichever half is leftmost (smallest x).
            area = min((target, new_areas[0]), key=lambda a: a.x)
            area.type = 'FILE_BROWSER'
            area.ui_type = 'ASSETS'

        # Selecting the library and refreshing must wait until the browser's `params`
        # exist (created lazily on the first redraw). Assigning `asset_library_reference`
        # can also no-op if the enum's items aren't populated yet, so verify the value
        # actually took and retry until it does, then refresh.
        attempts = [0]

        def _apply():
            w, a = self._find_asset_browser()
            if a is None:
                return None
            params = getattr(a.spaces.active, "params", None)
            if params is not None:
                try:
                    params.asset_library_reference = ASSET_LIB_NAME
                except TypeError:
                    pass  # enum items not built yet; retry below
            ready = params is not None and params.asset_library_reference == ASSET_LIB_NAME
            if not ready:
                attempts[0] += 1
                if attempts[0] > 40:  # ~2s; give up but say so rather than fail silently
                    print(f"[quixel] Could not select the '{ASSET_LIB_NAME}' asset library.")
                    return None
                return 0.05  # retry until it sticks
            with bpy.context.temp_override(window=w, area=a):
                bpy.ops.asset.library_refresh()
            return None

        bpy.app.timers.register(_apply, first_interval=0.0)
        return {'FINISHED'}


class FILEBROWSER_OT_search_assets(bpy.types.Operator):
    bl_idname = "filebrowser.search_assets"
    bl_label = "Search Assets"

    def execute(self, context):
        state.cancel_loading = True
        if state.loading_thread and state.loading_thread.is_alive():
            state.loading_thread.join()
            print("Stopping existing loading thread...")
        state.cancel_loading = False
        # Fresh search: clear the accumulated placeholder manifest and reset paging.
        state.manifest.clear()
        state.cursors["curr_cursor"] = "0"
        state.cursors["next_cursor"] = "0"
        error = update_assets(context, "0")
        if error:
            self.report({'ERROR'}, error)
            return {'CANCELLED'}
        self.report({'INFO'}, "Loading assets… results will appear in the Asset Browser.")
        return {'FINISHED'}


class FILEBROWSER_OT_load_more(bpy.types.Operator):
    bl_idname = "filebrowser.load_more"
    bl_label = "Load More"

    def execute(self, context):
        state.cancel_loading = True
        if state.loading_thread and state.loading_thread.is_alive():
            state.loading_thread.join()
        state.cancel_loading = False
        if state.cursors["next_cursor"] is not None:
            state.cursors["curr_cursor"] = state.cursors["next_cursor"]
            error = update_assets(context, state.cursors["curr_cursor"])
            if error:
                self.report({'ERROR'}, error)
                return {'CANCELLED'}
            self.report({'INFO'}, "Loading more assets")
        else:
            self.report({'INFO'}, "No more assets to load")
        return {'FINISHED'}


class FILEBROWSER_OT_clear_thumbnails(bpy.types.Operator):
    bl_idname = "filebrowser.clear_thumbnails"
    bl_label = "Clear Thumbnail Cache"
    bl_description = "Delete all downloaded thumbnail images"

    def execute(self, context):
        clear_thumbnail_cache(context)
        self.report({'INFO'}, "Thumbnail cache cleared.")
        return {'FINISHED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)


class FILEBROWSER_OT_clear_jsonfiles(bpy.types.Operator):
    bl_idname = "filebrowser.clear_jsonfiles"
    bl_label = "Clear JSON Cache"
    bl_description = "Delete all search data json files"

    def execute(self, context):
        clear_jsonfile_cache(context)
        self.report({'INFO'}, "JSON cache cleared.")
        return {'FINISHED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)


class FILEBROWSER_OT_clear_zipfiles(bpy.types.Operator):
    bl_idname = "filebrowser.clear_zipfiles"
    bl_label = "Clear ZIP Cache"
    bl_description = "Delete all downloaded asset zip files"

    def execute(self, context):
        clear_zipfile_cache(context)
        self.report({'INFO'}, "ZIP cache cleared.")
        return {'FINISHED'}

    def invoke(self, context, event):
        return context.window_manager.invoke_confirm(self, event)


class PREFERENCES_OT_update_data_path(bpy.types.Operator):
    bl_idname = "preferences.update_data_path"
    bl_label = "Update Asset Data Path"

    def execute(self, context):
        update_asset_data_path(context.preferences.addons[ADDON_ID].preferences, context)
        self.report({'INFO'}, "Asset data path updated.")
        return {'FINISHED'}


class PREFERENCES_OT_setup_env(bpy.types.Operator):
    bl_idname = "preferences.setup_env"
    bl_label = "Setup Environment"

    def execute(self, context):
        setup_env(context, reset=True)
        self.report({'INFO'}, "Environment setup complete.")
        return {'FINISHED'}


class FILEBROWSER_OT_set_asset_type(bpy.types.Operator):
    bl_idname = "filebrowser.set_asset_type"
    bl_label = "Set Asset Type"
    asset_type: bpy.props.StringProperty()

    def execute(self, context):
        context.scene.asset_type = self.asset_type
        bpy.ops.filebrowser.search_assets()
        return {'FINISHED'}


class FILEBROWSER_OT_set_import_type(bpy.types.Operator):
    bl_idname = "filebrowser.set_import_type"
    bl_label = "Set Import Type"
    import_type: bpy.props.StringProperty()

    def execute(self, context):
        context.scene.import_type = self.import_type
        return {'FINISHED'}


class FILEBROWSER_OT_set_import_size(bpy.types.Operator):
    bl_idname = "filebrowser.set_import_size"
    bl_label = "Set Import Size"
    import_size: bpy.props.StringProperty()

    def execute(self, context):
        context.scene.import_size = self.import_size
        return {'FINISHED'}
