"""All addon operators.

Grouped here: the two import operators (online asset and already-downloaded
asset), the search / load-more / mode-and-filter toggles that drive the panel, the
cache-clearing operators, and the two preference operators (update data path, setup
env). UI toggles simply write ``context.scene.*`` properties; the heavier operators
delegate to :mod:`.assets`, :mod:`.importer` and :mod:`.paths`.

Shared runtime state (queue, threads, cancel flag, preview collection, the visible
``assets`` dict) is mutated through :mod:`.state`.

Depends on :mod:`.constants`, :mod:`.state`, :mod:`.paths`, :mod:`.assets` and
:mod:`.importer`.
"""

import json
import os
import subprocess
import threading
from datetime import datetime, timezone

import bpy

from . import state
from .constants import ADDON_ID, ASSET_IMPORTER_SCRIPT, FAB_API_SCRIPT
from .paths import (
    clear_jsonfile_cache,
    clear_thumbnail_cache,
    clear_zipfile_cache,
    get_asset_paths,
    is_valid_python_path,
    setup_env,
    update_asset_data_path,
)
from .assets import add_downloaded_asset, update_assets
from .importer import import_to_scene, update_ui_with_progress


class IMPORT_ASSET_OT_import_asset(bpy.types.Operator):
    bl_idname = "import_asset.import"
    bl_label = "Import Asset"
    asset_name: bpy.props.StringProperty()
    uid: bpy.props.StringProperty()
    img_path: bpy.props.StringProperty()

    def execute(self, context):
        bpy.context.window.cursor_set('WAIT')
        print(f"Importing Asset: {self.asset_name}")
        print(f"UID: {self.uid}")
        print(f"Image Path: {self.img_path if self.img_path else 'No Image Available'}")
        paths = get_asset_paths(context)
        if not is_valid_python_path(context.preferences.addons[ADDON_ID].preferences.system_python):
            self.report({'ERROR'}, "Invalid or unset Python path. Please set a valid Python executable in preferences.")
            bpy.context.window.cursor_set('DEFAULT')
            return {'CANCELLED'}
        asset_type = str(context.scene.asset_type).strip()
        asset_formats_file = os.path.join(paths["json_dir"], f"asset_{self.uid}.json")

        if not os.path.exists(asset_formats_file):
            url = f"https://www.fab.com/i/listings/{self.uid}/asset-formats"
            referer = f"https://www.fab.com/i/listings/{self.uid}"
            command = [paths["python_path"], FAB_API_SCRIPT, "--function", "fetch_asset_formats", url, referer,
                       paths["json_dir"], self.uid]
            print(f"Running {command} inside the virtual environment...")
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            print(process.communicate()[0])

        if not os.path.exists(asset_formats_file):
            self.report({'ERROR'}, "Could not fetch asset formats from fab.com. "
                                   "Check your connection and that you're logged into fab.com in Chrome or Firefox.")
            bpy.context.window.cursor_set('DEFAULT')
            return {'CANCELLED'}
        with open(asset_formats_file, "r") as f:
            data = json.load(f)
        asset_name = None
        asset_uid = None
        asset_format = {'3d-model': 'fbx', 'material': 'texture-set', 'decal': 'texture-set'}.get(asset_type)
        if asset_format:
            import_size = int(context.scene.import_size.strip())
            for asset in data:
                if asset["assetFormatType"]["code"] == asset_format:
                    while import_size >= 0:
                        try:
                            asset_name = asset["files"][import_size]["name"]
                            break
                        except IndexError:
                            import_size -= 1
                    asset_uid = asset["files"][import_size]["uid"]
            print(f"UID for {asset_format}: {asset_uid}")
            if not asset_uid:
                self.report({'ERROR'}, f"{asset_format} not found")
                bpy.context.window.cursor_set('DEFAULT')
                return {'CANCELLED'}
            asset_path = os.path.join(paths["assets_dir"], asset_name)
            extract_name = os.path.splitext(asset_name)[0]
            extract_path = os.path.join(paths["unzipped_assets_dir"], extract_name)
            if not os.path.exists(extract_path):
                if not os.path.exists(asset_path):
                    down_link_file = os.path.join(paths["json_dir"], f"downlink_{asset_uid}.json")
                    link_expired = True
                    if os.path.exists(down_link_file):
                        with open(down_link_file, "r") as f:
                            data = json.load(f)
                        expires_dt = datetime.fromisoformat(data["downloadInfo"][0]["expires"].rstrip("Z")).replace(
                            tzinfo=timezone.utc)
                        link_expired = datetime.now(timezone.utc) > expires_dt
                    if link_expired:
                        url = f"https://www.fab.com/i/listings/{self.uid}/asset-formats/{asset_format}/files/{asset_uid}/download-info"
                        referer = f"https://www.fab.com/i/listings/{self.uid}"
                        command = [paths["python_path"], FAB_API_SCRIPT, "--function", "fetch_down_link", url, referer,
                                   paths["json_dir"], asset_uid]
                        print(f"Running {command} inside the virtual environment...")
                        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                        print(process.communicate()[0])
                    if not os.path.exists(down_link_file):
                        self.report({'ERROR'}, "Could not get a download link. Log into fab.com in Chrome or "
                                               "Firefox, make sure the asset is in your library, then try again.")
                        bpy.context.window.cursor_set('DEFAULT')
                        return {'CANCELLED'}
                    with open(down_link_file, "r") as f:
                        data = json.load(f)
                        down_link = data["downloadInfo"][0]["downloadUrl"]
                    command = [paths["python_path"], FAB_API_SCRIPT, "--function", "download_file", down_link, asset_path]
                    print(f"Running {command} inside the virtual environment...")
                    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                    progress_thread = threading.Thread(target=update_ui_with_progress, args=(process,))
                    progress_thread.start()
                    progress_thread.join()
                    print('\n')
                else:
                    print(f"ZIP file already exists: {asset_path}")
            else:
                print(f"Unzipped folder already exists: {extract_path}")

            add_downloaded_asset(context, asset_uid, self.asset_name, asset_type, asset_path, import_size,
                                 self.img_path)
            if context.scene.import_type == "import_to_scene":
                import_result = import_to_scene(context, asset_name, asset_path, asset_type)
                if import_result != 0:
                    self.report({'INFO'}, "Asset Import Failed")
                    return {'FINISHED'}
            elif context.scene.import_type == "add_to_asset_library":
                prefs = context.preferences.addons[ADDON_ID].preferences
                blender_path = prefs.blender_executable_path
                if not blender_path or not os.path.isfile(blender_path):
                    self.report({"ERROR"}, "Invalid Blender executable path!")
                    return {'CANCELLED'}
                command = [blender_path, "-b", "--factory-startup", "-P", ASSET_IMPORTER_SCRIPT, "--",
                           paths["assets_dir"], asset_name, asset_path, asset_type, self.img_path]
                process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                com = process.communicate()[0]
                if process.returncode != 0:
                    print("Error Importing and Marking Asset")
                else:
                    print(str(com))
                    for area in bpy.context.screen.areas:
                        if area.type == 'FILE_BROWSER':
                            with bpy.context.temp_override(area=area):
                                bpy.ops.asset.library_refresh()
                            break
        bpy.context.window.cursor_set('DEFAULT')
        self.report({'INFO'}, "Asset Imported")
        return {'FINISHED'}


class IMPORT_DOWNLOADED_ASSET_OT_import(bpy.types.Operator):
    bl_idname = "import_downloaded_asset.import"
    bl_label = "Import Downloaded Asset"
    asset_uid: bpy.props.StringProperty()
    asset_name: bpy.props.StringProperty()
    asset_type: bpy.props.StringProperty()
    asset_path: bpy.props.StringProperty()
    thumbnail_path: bpy.props.StringProperty()
    import_method: bpy.props.StringProperty()

    def execute(self, context):
        paths = get_asset_paths(context)
        if self.import_method == "import_to_scene":
            import_result = import_to_scene(context, self.asset_name, self.asset_path, self.asset_type)
            if import_result != 0:
                self.report({'INFO'}, "Asset Import Failed")
                return {'FINISHED'}
        elif self.import_method == "add_to_asset_library":
            prefs = context.preferences.addons[ADDON_ID].preferences
            blender_path = prefs.blender_executable_path
            if not blender_path or not os.path.isfile(blender_path):
                self.report({"ERROR"}, "Invalid Blender executable path!")
                return {'CANCELLED'}
            command = [blender_path, "-b", "--factory-startup", "-P", ASSET_IMPORTER_SCRIPT, "--", paths["assets_dir"],
                       self.asset_name, self.asset_path, self.asset_type, self.thumbnail_path]
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            com = process.communicate()[0]
            if process.returncode != 0:
                print("Error Importing and Marking Asset")
            else:
                print(str(com))
                for area in bpy.context.screen.areas:
                    if area.type == 'FILE_BROWSER':
                        with bpy.context.temp_override(area=area):
                            bpy.ops.asset.library_refresh()
                        break
        self.report({'INFO'}, "Asset Imported")
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
        with state.asset_queue.mutex:
            state.asset_queue.queue.clear()
        if state.preview_collection:
            state.preview_collection.clear()
        state.assets = {}
        cursor = "0"
        update_assets(context, cursor)
        try:
            self.report({'INFO'}, "Loading Assets List")
        except:
            pass
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
            self.report({'INFO'}, "Loading more assets")
            update_assets(context, state.cursors["curr_cursor"])
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


class FILEBROWSER_OT_set_asset_mode(bpy.types.Operator):
    bl_idname = "filebrowser.set_asset_mode"
    bl_label = "Set Asset Mode"
    asset_mode: bpy.props.StringProperty()

    def execute(self, context):
        if self.asset_mode == "downloaded":
            state.cancel_loading = True
            if state.loading_thread and state.loading_thread.is_alive():
                state.loading_thread.join()
                print("Stopping existing loading thread...")
            state.cancel_loading = False
            with state.asset_queue.mutex:
                state.asset_queue.queue.clear()
            if state.preview_collection:
                state.preview_collection.clear()
            state.assets = {}
            context.scene.asset_mode = self.asset_mode
        elif self.asset_mode == "online":
            context.scene.asset_mode = self.asset_mode
            bpy.ops.filebrowser.search_assets()
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


class FILEBROWSER_OT_set_downloaded_asset_type(bpy.types.Operator):
    bl_idname = "filebrowser.set_downloaded_asset_type"
    bl_label = "Set Downloaded Asset Type"
    asset_type: bpy.props.StringProperty()

    def execute(self, context):
        context.scene.downloaded_asset_type = self.asset_type
        return {'FINISHED'}


class FILEBROWSER_OT_set_downloaded_import_size(bpy.types.Operator):
    bl_idname = "filebrowser.set_downloaded_import_size"
    bl_label = "Set Downloaded Import Size"
    import_size: bpy.props.StringProperty()

    def execute(self, context):
        context.scene.downloaded_import_size = self.import_size
        return {'FINISHED'}


class FILEBROWSER_OT_set_downloaded_import_method(bpy.types.Operator):
    bl_idname = "filebrowser.set_downloaded_import_method"
    bl_label = "Set Downloaded Import Method"
    import_method: bpy.props.StringProperty()

    def execute(self, context):
        context.scene.downloaded_import_method = self.import_method
        return {'FINISHED'}
