import bpy
import bpy.utils.previews
import json
import os
import queue
import subprocess
import threading
from datetime import datetime, timezone
import zipfile

current_file_path = bpy.context.space_data.text.filepath
current_file_dir = os.sep.join(current_file_path.split(os.sep)[:-1])
utils_path = os.path.join(current_file_dir, "utils.py")
asset_importer_path = os.path.join(current_file_dir, "asset_importer.py")

asset_queue = queue.Queue()
loading_thread = None

system_python = "/usr/bin/python3"
env_dir = "/tmp/tmp-env"
python_path = os.path.join(env_dir, "bin", "python")
blender_path = "/opt/blender_builds/blender-4.2-lts/blender"

data_dir = "/tmp/fab_data"
thumbnail_dir = os.path.join(data_dir, "thumbnails")
assets_dir = os.path.join(data_dir, "assets")
unzipped_assets_dir = os.path.join(assets_dir, "unzipped_assets")
blender_files_dir = os.path.join(assets_dir, "blender_files")
catalog_file = os.path.join(assets_dir, "blender_assets.cats.txt")

os.makedirs(data_dir, exist_ok=True)
os.makedirs(thumbnail_dir, exist_ok=True)
os.makedirs(assets_dir, exist_ok=True)
os.makedirs(unzipped_assets_dir, exist_ok=True)
os.makedirs(blender_files_dir, exist_ok=True)

asset_library_paths = [library.path for library in bpy.context.preferences.filepaths.asset_libraries]
if assets_dir not in asset_library_paths:
    bpy.ops.preferences.asset_library_add(directory=assets_dir)

cursors = {"curr_cursor" : "0", "next_cursor" : "0"}



def setup_env():
    if not os.path.exists(env_dir):
        print(f"Creating virtual environment at {env_dir}")
        subprocess.check_call([system_python, "-m", "venv", env_dir])
        subprocess.check_call([python_path, "-m", "pip", "install", "--upgrade", "pip"])
        subprocess.check_call([python_path, "-m", "pip", "install", "requests", "zstandard", "pillow"])


def update_assets(context, cursor):
    global loading_thread

    asset_type = str(context.scene.asset_type).strip()
    print(asset_type)
    query = context.scene.asset_search.strip()
    # cursor = cursors["curr_cursor"].strip()
    file_path = os.path.join(data_dir, f"output_{asset_type}_{query}_{cursor}.json")

    if not os.path.exists(file_path):
        url = "https://www.fab.com/i/listings/search"
        referer = "https://www.fab.com/sellers/Quixel"

        print(f"Running {utils_path} inside the virtual environment...")
        command = [python_path, utils_path, "--function", "fetch_assets", url, referer, asset_type, query, cursor,]
        # result = subprocess.run(command, capture_output=True, text=True)
        # print(result)
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        print(process.communicate())

    # Stop any existing thread
    if loading_thread and loading_thread.is_alive():
        print("Stopping existing loading thread...")
        loading_thread.join()

    # Clear old assets and start a new thread
    # FILEBROWSER_PT_assets.assets = None
    loading_thread = threading.Thread(target=load_assets_in_background, args=(file_path,asset_type,))
    loading_thread.start()

    # Start UI timer to process the queue
    bpy.app.timers.register(update_ui_from_queue)


def load_assets_in_background(file_path,asset_type):
    pcoll = bpy.utils.previews.new()

    with open(file_path, 'r') as f:
        data = json.load(f)

    cursor_data = data.get("cursors", {})
    cursors["next_cursor"] = cursor_data.get("next")

    results_data = data.get("results", [])

    for item in results_data:
        asset_name = item.get("title", "")
        uid = item.get("uid", "")
        # img_url = item["thumbnails"][0]["mediaUrl"]
        img_url = next((img["url"] for img in item["thumbnails"][0]["images"] if img["height"] == 180), None)
        # img_name = item["thumbnails"][0]["name"]
        if img_url:
            img_name = os.path.basename(img_url)
            img_path = os.path.join(thumbnail_dir, img_name)
        else:
            img_name = "unknown.jpg"
            img_path = None

        # Download the image if not already present
        if img_path and not os.path.exists(img_path):
            subprocess.check_call(["curl", "-o", img_path, img_url])
            if asset_type in ('material', 'decal'):
                print(f"Running {utils_path} inside the virtual environment...")
                command = [python_path, utils_path, "--function", "crop_thumbnails", img_path,]
                # result = subprocess.run(command, capture_output=True, text=True)
                # print(result)
                process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                print(process.communicate())

        # Load the asset into the preview collection
        if img_path and os.path.exists(img_path):
            pcoll.load(uid, img_path, 'IMAGE')
            # Add the asset to the queue
            asset_queue.put((asset_name, uid, img_path, pcoll[uid]))
        else:
            print(f"Image path {img_path} does not exist.")

    # Signal completion
    asset_queue.put(None)


def update_ui_from_queue():
    if FILEBROWSER_PT_assets.assets is None:
        FILEBROWSER_PT_assets.assets = bpy.utils.previews.new()

    while not asset_queue.empty():
        item = asset_queue.get()
        if item is None:  # Stop signal
            print("Asset loading complete.")
            return None
        asset_name, uid, img_path, asset = item  # Ensure the queue holds correct values
        FILEBROWSER_PT_assets.assets[uid] = {"preview": asset, "img_path": img_path, "asset_name": asset_name}
    return 0.1


def import_to_scene(asset_name, asset_path, asset_type):
    print(asset_name)
    print(asset_path)

    if asset_path.endswith(".zip"):
        extract_path = os.path.join(unzipped_assets_dir, asset_name)
        # Check if the asset is already unzipped
        if not os.path.exists(extract_path):
            try:
                with zipfile.ZipFile(asset_path, 'r') as zip_ref:
                    zip_ref.extractall(extract_path)
                print(f"Extracted {asset_name} to {extract_path}")
            except zipfile.BadZipFile:
                print(f"{asset_name} is not a valid ZIP file.")
                return
        else:
            print(f"Asset '{asset_name}' is already unzipped. Skipping extraction.")

        if asset_type == '3d-model':
            for file_name in os.listdir(extract_path):
                if file_name.endswith(".fbx"):
                    fbx_path = os.path.join(extract_path, file_name)

                    # Import the fbx file
                    bpy.ops.import_scene.fbx(filepath=fbx_path)
                    print(f"Imported FBX: {fbx_path}")

                    # Create a collection for the asset
                    new_collection = bpy.data.collections.new(asset_name)
                    bpy.context.scene.collection.children.link(new_collection)

                    # Move imported objects to the new collection
                    for obj in bpy.context.selected_objects:
                        bpy.context.scene.collection.objects.unlink(obj)
                        new_collection.objects.link(obj)

                        # Apply transforms
                        bpy.context.view_layer.objects.active = obj
                        bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

                        material_name = obj.name + "_mat"
                        material = bpy.data.materials.get(material_name)
                        if not material:
                            material = bpy.data.materials.new(name=material_name)
                            create_pbr_shader(material, extract_path)
                        obj.data.materials.clear()
                        obj.data.materials.append(material)
        else:
            # Implement import of other asset types
            pass


def create_pbr_shader(material, texture_maps_path):
    # Enable 'Use Nodes' for the material
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links

    # Clear default nodes
    for node in nodes:
        nodes.remove(node)

    # Create a Principled BSDF shader
    principled_bsdf = nodes.new(type='ShaderNodeBsdfPrincipled')
    principled_bsdf.location = (200, 0)

    # Create Material Output node
    material_output = nodes.new(type='ShaderNodeOutputMaterial')
    material_output.location = (600, 0)

    # Link the Principled BSDF to the Material Output
    links.new(principled_bsdf.outputs['BSDF'], material_output.inputs['Surface'])

    # Define texture map keywords
    texture_map_keywords = {
        'Base Color': 'BaseColor',
        'Metallic': 'Metalness',
        'Normal': 'Normal',
        'Roughness': 'Roughness',
        'Specular': 'Specular',
        'AO': 'AO',
        'Bump': 'Bump'
    }

    # Get all jpg files in the specified directory
    texture_files = [f for f in os.listdir(texture_maps_path) if f.endswith('.jpg')]

    # Create nodes for AO and Bump mapping
    mix_rgb = nodes.new(type='ShaderNodeMixRGB')
    mix_rgb.blend_type = 'MULTIPLY'
    mix_rgb.location = (-200, 0)

    bump_node = nodes.new(type='ShaderNodeBump')
    bump_node.inputs['Strength'].default_value = 0.1
    bump_node.inputs['Distance'].default_value = 0.1
    bump_node.location = (-200, -200)

    normal_map = nodes.new(type='ShaderNodeNormalMap')
    normal_map.location = (-400, -200)

    # Load and set up texture maps
    texture_nodes = {}
    y_offset = 0  # Start Y-position for textures
    for map_type, keyword in texture_map_keywords.items():
        # Find the corresponding texture file
        texture_file = next((f for f in texture_files if keyword in f), None)
        if texture_file:
            texture_path = os.path.join(texture_maps_path, texture_file)
            if bpy.data.images.get(texture_file):
                image = bpy.data.images[texture_file]
            else:
                image = bpy.data.images.load(texture_path)

            # Create an Image Texture node
            image_texture = nodes.new(type='ShaderNodeTexImage')
            image_texture.label = map_type
            image_texture.image = image
            image_texture.location = (-750, y_offset)
            y_offset -= 300  # Move the next texture down

            # Set 'Non-Color' for specific maps
            if map_type in ['Roughness', 'Metallic', 'Normal', 'Specular', 'AO', 'Bump']:
                image.colorspace_settings.name = 'Non-Color'

            texture_nodes[map_type] = image_texture

    # Connect Base Color
    if 'Base Color' in texture_nodes:
        links.new(texture_nodes['Base Color'].outputs['Color'], mix_rgb.inputs[1])

    # Connect AO to MixRGB
    if 'AO' in texture_nodes:
        links.new(texture_nodes['AO'].outputs['Color'], mix_rgb.inputs[2])

    # Connect MixRGB output to Principled BSDF Base Color
    links.new(mix_rgb.outputs['Color'], principled_bsdf.inputs['Base Color'])

    # Connect Roughness
    if 'Roughness' in texture_nodes:
        links.new(texture_nodes['Roughness'].outputs['Color'], principled_bsdf.inputs['Roughness'])

    # Connect Metallic
    if 'Metallic' in texture_nodes:
        links.new(texture_nodes['Metallic'].outputs['Color'], principled_bsdf.inputs['Metallic'])

    # Connect Specular
    if 'Specular' in texture_nodes:
        links.new(texture_nodes['Specular'].outputs['Color'], principled_bsdf.inputs['Specular IOR Level'])

    # Connect Normal and Bump
    if 'Normal' in texture_nodes:
        links.new(texture_nodes['Normal'].outputs['Color'], normal_map.inputs['Color'])

    if 'Bump' in texture_nodes:
        links.new(texture_nodes['Bump'].outputs['Color'], bump_node.inputs['Height'])

    # Connect Bump to Normal and then to Principled BSDF
    links.new(normal_map.outputs['Normal'], bump_node.inputs['Normal'])
    links.new(bump_node.outputs['Normal'], principled_bsdf.inputs['Normal'])


### Operators and Properties ###

class FILEBROWSER_PT_assets(bpy.types.Panel):
    bl_label = "Quixel Assets"
    bl_idname = "FILEBROWSER_PT_assets"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Quixel'

    assets = None

    def draw(self, context):
        layout = self.layout
        layout.alignment = "CENTER"

        # Three buttons for asset type
        row = layout.row(align=True)
        row.operator("filebrowser.set_asset_type", text="3D Model", depress=context.scene.asset_type == '3d-model').asset_type = '3d-model'
        row.operator("filebrowser.set_asset_type", text="Material", depress=context.scene.asset_type == 'material').asset_type = 'material'
        row.operator("filebrowser.set_asset_type", text="Decal", depress=context.scene.asset_type == 'decal').asset_type = 'decal'

        # Search box and search button
        row = layout.row()
        row.prop(context.scene, "asset_search", text="")
        row.operator("filebrowser.search_assets", text="", icon='VIEWZOOM')

        # Add checkboxes for Import Asset and Create Asset
        row = layout.row()
        row.prop(context.scene, "instance_to_scene")
        row.prop(context.scene, "add_to_asset_library")

        if self.assets:
            row = layout.row()
            # Calculate the number of columns based on the panel's width
            min_width = 120  # Minimum width for a single column
            columns_count = max(1, min(int(context.region.width / min_width), len(self.assets)))
            column_list = [row.column(align=True) for _ in range(columns_count)]

            for i, (uid, asset_data) in enumerate(self.assets.items()):
                col = column_list[i % columns_count]
                asset_box = col.box()
                asset_box.scale_x = 1.0
                asset_box.scale_y = 1.0

                preview = asset_data["preview"]
                img_path = asset_data["img_path"]
                asset_name = asset_data["asset_name"]

                asset_box.template_icon(preview.icon_id, scale=5)
                asset_box.label(text=asset_name, icon='BLANK1')

                # Add Import Button
                import_btn = asset_box.operator("import_asset.import", text="Import")
                import_btn.asset_name = asset_name
                import_btn.uid = uid
                import_btn.img_path = img_path if img_path else "No Image"

        row = layout.row()
        row.operator("filebrowser.load_more", text="Load More")


class IMPORT_ASSET_OT_import_asset(bpy.types.Operator):
    """Import Asset"""
    bl_idname = "import_asset.import"
    bl_label = "Import Asset"

    asset_name: bpy.props.StringProperty()
    uid: bpy.props.StringProperty()
    img_path: bpy.props.StringProperty()

    def execute(self, context):
        print(f"Importing Asset: {self.asset_name}")
        print(f"UID: {self.uid}")
        print(f"Image Path: {self.img_path if self.img_path else 'No Image Available'}")

        asset_type = str(context.scene.asset_type).strip()
        asset_formats_file = os.path.join(data_dir, f"output_{self.uid}.json")

        if not os.path.exists(asset_formats_file):
            url = f"https://www.fab.com/i/listings/{self.uid}/asset-formats"
            referer = "https://www.fab.com/sellers/Quixel"

            print(f"Running {utils_path} inside the virtual environment...")
            command = [python_path, utils_path, "--function", "fetch_asset_formats", url, referer, self.uid ]
            # result = subprocess.run(command, capture_output=True, text=True)
            # print(result)
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            print(process.communicate())

        with open(asset_formats_file, "r") as f:
            data = json.load(f)
        asset_name = None
        asset_uid = None

        if asset_type == '3d-model':
            for asset in data:
                if asset["assetFormatType"]["code"] == "fbx":
                    asset_name = asset["files"][-1]["name"]
                    asset_uid = asset["files"][-1]["uid"]  # Get UID of last file
            print("Last UID for fbx:", asset_uid)

            asset_path = os.path.join(assets_dir, asset_name)

            if not os.path.exists(asset_path):
                down_link_file = os.path.join(data_dir, f"output_{asset_uid}.json")
                link_expired = True

                if os.path.exists(down_link_file):
                    with open(down_link_file, "r") as f:
                        data = json.load(f)
                    expires_dt = datetime.fromisoformat(data["downloadInfo"][0]["expires"].rstrip("Z")).replace(tzinfo=timezone.utc)
                    link_expired = datetime.now(timezone.utc) > expires_dt

                if link_expired:
                    url = f"https://www.fab.com/i/listings/{self.uid}/asset-formats/fbx/files/{asset_uid}/download-info/binary"
                    referer = f"https://www.fab.com/i/listings/{self.uid}"

                    print(f"Running {utils_path} inside the virtual environment...")
                    command = [python_path, utils_path, "--function", "fetch_down_link", url, referer, asset_uid]
                    # result = subprocess.run(command, capture_output=True, text=True)
                    # print(result)
                    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                    print(process.communicate())

                with open(down_link_file, "r") as f:
                    data = json.load(f)
                    down_link = data["downloadInfo"][0]["downloadUrl"]
                subprocess.check_call(["curl", "-o", asset_path, down_link])

            if context.scene.instance_to_scene:
                import_to_scene(asset_name, asset_path, asset_type)

        # subprocess.run(
        #     [blender_path, "-b", "--factory-startup", "-P", asset_importer_path, "--", assets_dir, asset_name, asset_path, self.img_path],
        #     check=True,
        # )

        # for area in bpy.context.screen.areas:
        #     if area.type == 'FILE_BROWSER':
        #         with bpy.context.temp_override(area=area):
        #             bpy.ops.asset.library_refresh()
        #         break

        self.report({'INFO'}, "Asset Imported")
        return {'FINISHED'}


class FILEBROWSER_OT_search_assets_modal(bpy.types.Operator):
    """Detect Enter Key Press for Search"""
    bl_idname = "filebrowser.search_assets_modal"
    bl_label = "Search Assets Modal"

    def modal(self, context, event):
        if event.type in {'RET', 'NUMPAD_ENTER'} and event.value == 'PRESS':
            bpy.ops.filebrowser.search_assets()
            return {'FINISHED'}
        return {'PASS_THROUGH'}

    def invoke(self, context, event):
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}


class FILEBROWSER_OT_search_assets(bpy.types.Operator):
    bl_idname = "filebrowser.search_assets"
    bl_label = "Search Assets"

    def execute(self, context):
        cursor = "0"
        FILEBROWSER_PT_assets.assets = None
        update_assets(context, cursor)
        return {'FINISHED'}


class FILEBROWSER_OT_load_more(bpy.types.Operator):
    bl_idname = "filebrowser.load_more"
    bl_label = "Load More"

    def execute(self, context):
        if cursors["next_cursor"] is not None:
            cursors["curr_cursor"] = cursors["next_cursor"]
            self.report({'INFO'}, "Loading more assets")
            update_assets(context, cursors["curr_cursor"])
        return {'FINISHED'}


class FILEBROWSER_OT_set_asset_type(bpy.types.Operator):
    bl_idname = "filebrowser.set_asset_type"
    bl_label = "Set Asset Type"

    asset_type: bpy.props.StringProperty()

    def execute(self, context):
        context.scene.asset_type = self.asset_type
        bpy.ops.filebrowser.search_assets()
        return {'FINISHED'}


def register():
    bpy.utils.register_class(FILEBROWSER_PT_assets)
    bpy.utils.register_class(FILEBROWSER_OT_load_more)
    bpy.utils.register_class(IMPORT_ASSET_OT_import_asset)
    bpy.utils.register_class(FILEBROWSER_OT_search_assets)
    bpy.utils.register_class(FILEBROWSER_OT_search_assets_modal)
    bpy.utils.register_class(FILEBROWSER_OT_set_asset_type)

    # bpy.types.Scene.asset_search = bpy.props.StringProperty(name="Search Assets")
    bpy.types.Scene.asset_search = bpy.props.StringProperty(
        name="Search Assets",
        update=FILEBROWSER_OT_search_assets.execute
    )

    bpy.types.Scene.asset_type = bpy.props.StringProperty(
        name="Asset Type",
        default='3d-model'
    )

    bpy.types.Scene.instance_to_scene = bpy.props.BoolProperty(
        name="Instance to Scene",
        description="Instance to current scene",
        default=True
    )

    bpy.types.Scene.add_to_asset_library = bpy.props.BoolProperty(
        name="Add to Asset Library",
        description="Add to Asset Library",
        default=False
    )

    FILEBROWSER_PT_assets.assets = bpy.utils.previews.new()
    # bpy.ops.filebrowser.search_assets_modal()
    setup_env()


def unregister():
    bpy.utils.unregister_class(FILEBROWSER_PT_assets)
    bpy.utils.unregister_class(FILEBROWSER_OT_load_more)
    bpy.utils.unregister_class(IMPORT_ASSET_OT_import_asset)
    bpy.utils.unregister_class(FILEBROWSER_OT_search_assets)
    bpy.utils.unregister_class(FILEBROWSER_OT_search_assets_modal)
    bpy.utils.unregister_class(FILEBROWSER_OT_set_asset_type)

    del bpy.types.Scene.asset_search
    del bpy.types.Scene.asset_type
    del bpy.types.Scene.instance_to_scene
    del bpy.types.Scene.add_to_asset_library

    # Clean up previews to avoid memory leaks
    if FILEBROWSER_PT_assets.assets:
        bpy.utils.previews.remove(FILEBROWSER_PT_assets.assets)
        FILEBROWSER_PT_assets.assets = None


if __name__ == "__main__":
    register()
