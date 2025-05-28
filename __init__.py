import bpy
import bpy.utils.previews
import json
import os
import queue
import subprocess
import threading
from datetime import datetime, timezone, timedelta
import zipfile
import uuid
import platform


bl_info = {
    "name": "Fab to Blender",
    "description": "Browse and import free quixel assets from fab.com",
    "author": "https://github.com/cgmaterial",
    "version": (2, 1, 0),
    "blender": (4, 4, 3),
    "location": "View3D > Sidebar > Quixel",
    "category": "Asset Management",
}

current_file_dir = os.path.join(os.path.dirname(__file__))
utils_path = os.path.join(current_file_dir, "tools", "utils.py")
asset_importer_path = os.path.join(current_file_dir, "tools", "asset_importer.py")
preview_img = os.path.join(current_file_dir, "images", "preview.svg")

def_blender_executable_path = bpy.app.binary_path
def_asset_data_path = ""
system_python = ""
env_dir = ""
python_path = ""

if platform.system() == 'Windows':
    def_asset_data_path = os.path.join(os.getenv('USERPROFILE'), 'Documents')
    system_python = subprocess.check_output(['where', 'python3']).strip().decode('utf-8')
    env_dir = os.path.join(def_asset_data_path, "fab-env")
    python_path = os.path.join(env_dir, "Scripts", "python")
else:
    def_asset_data_path = os.path.join(os.getenv('HOME'), 'Documents')
    system_python = subprocess.check_output(['which', 'python3']).strip().decode('utf-8')
    env_dir = os.path.join(def_asset_data_path, "fab-env")
    python_path = os.path.join(env_dir, "bin", "python")

asset_lib_name = "Quixel Assets"
data_dir = os.path.join(def_asset_data_path, "fab_data")
thumbnail_dir = os.path.join(data_dir, "thumbnails")
assets_dir = os.path.join(data_dir, "quixel_assets")
json_dir = os.path.join(data_dir, "json_files")
unzipped_assets_dir = os.path.join(assets_dir, "unzipped_assets")
blender_files_dir = os.path.join(assets_dir, "blender_files")
catalog_file = os.path.join(assets_dir, "blender_assets.cats.txt")
downloaded_assets_file = os.path.join(assets_dir, "downloaded_assets.json")

asset_queue = queue.Queue()
loading_thread = None
cursors = {"curr_cursor": "0", "next_cursor": "0"}
preview_collection = None
cancel_loading = False


class AssetProcessorPreferences(bpy.types.AddonPreferences):
    """Preferences for the addon"""
    bl_idname = __name__

    blender_executable_path: bpy.props.StringProperty(
        name="Blender Executable Path",
        description="Path to the Blender executable",
        subtype='FILE_PATH',
        default=def_blender_executable_path,
    )

    asset_data_path: bpy.props.StringProperty(
        name="Asset Data Path",
        description="Path to save assets data",
        subtype='DIR_PATH',
        default=def_asset_data_path,
        update=lambda self, context: update_asset_data_path(self, context)
    )

    def draw(self, context):
        layout = self.layout
        layout.prop(self, "blender_executable_path")
        layout.prop(self, "asset_data_path")


def initialize_paths():
    os.makedirs(data_dir, exist_ok=True)
    os.makedirs(thumbnail_dir, exist_ok=True)
    os.makedirs(assets_dir, exist_ok=True)
    os.makedirs(json_dir, exist_ok=True)
    os.makedirs(unzipped_assets_dir, exist_ok=True)
    os.makedirs(blender_files_dir, exist_ok=True)

    if not os.path.exists(catalog_file):
        with open(catalog_file, 'w') as f:
            f.write(f"VERSION 1\n{str(uuid.uuid4())}:3d:3d\n{str(uuid.uuid4())}:surface:surface\n")

    asset_library_paths = [library.path for library in bpy.context.preferences.filepaths.asset_libraries]
    if assets_dir not in asset_library_paths:
        bpy.app.timers.register(add_asset_library, first_interval=1.0)


def add_asset_library():
    try:
        bpy.ops.preferences.asset_library_add()
        asset_library = bpy.context.preferences.filepaths.asset_libraries[-1]
        asset_library.name = asset_lib_name
        asset_library.path = assets_dir
        print(f"Asset library added: {assets_dir}")
    except Exception as e:
        print(f"Failed to add asset library: {e}")
    return None  # Stop the timer


def update_asset_data_path(self, context):
    global data_dir, thumbnail_dir, assets_dir, json_dir, unzipped_assets_dir, blender_files_dir, catalog_file, downloaded_assets_file

    data_dir = os.path.join(self.asset_data_path, "fab_data")
    thumbnail_dir = os.path.join(data_dir, "thumbnails")
    assets_dir = os.path.join(data_dir, "quixel_assets")
    json_dir = os.path.join(data_dir, "json_files")
    unzipped_assets_dir = os.path.join(assets_dir, "unzipped_assets")
    blender_files_dir = os.path.join(assets_dir, "blender_files")
    catalog_file = os.path.join(assets_dir, "blender_assets.cats.txt")
    downloaded_assets_file = os.path.join(assets_dir, "downloaded_assets.json")

    # Reinitialize directories
    initialize_paths()

    print("Updated asset data path and dependent paths.")


def setup_env():
    if not os.path.exists(env_dir):
        print(f"Creating virtual environment at {env_dir}")
        subprocess.check_call([system_python, "-m", "venv", env_dir])
        subprocess.check_call([python_path, "-m", "pip", "install", "--upgrade", "pip"])
        subprocess.check_call([python_path, "-m", "pip", "install", "requests", "cloudscraper", "zstandard", "pillow"])


def initialize_preview_collection():
    global preview_collection, preview_img
    if not preview_collection:
        preview_collection = bpy.utils.previews.new()
        preview_collection.load("preview", preview_img, 'IMAGE')

    # Load thumbnails for downloaded assets
    downloaded_assets = load_downloaded_assets()
    for uid, asset_data in downloaded_assets.items():
        thumbnail_path = asset_data["thumbnail_image"]
        if os.path.exists(thumbnail_path):
            preview_collection.load(uid, thumbnail_path, 'IMAGE')


def cleanup_preview_collection():
    global preview_collection
    if preview_collection:
        bpy.utils.previews.remove(preview_collection)
        preview_collection = None


def fix_asset_paths():
    for item in os.listdir(unzipped_assets_dir):
        if item and os.path.isdir(os.path.join(unzipped_assets_dir, item)):
            if item.endswith(".zip"):
                new_name = item[:-4]
                old_path = os.path.join(unzipped_assets_dir, item)
                new_path = os.path.join(unzipped_assets_dir, new_name)
                os.rename(old_path, new_path)
                print(f"Renamed folder: {item} -> {new_name}")


def clear_thumbnail_cache():
    for item in os.listdir(thumbnail_dir):
        thumbnail = os.path.join(thumbnail_dir, item)
        if item and os.path.isfile(thumbnail):
            os.remove(thumbnail)
            print(f"Removed thumbnail: {thumbnail}")


def load_downloaded_assets():
    """Load the downloaded assets from the JSON file."""
    if os.path.exists(downloaded_assets_file):
        with open(downloaded_assets_file, 'r') as f:
            return json.load(f)
    return {}


def save_downloaded_assets(assets):
    """Save the downloaded assets to the JSON file."""
    with open(downloaded_assets_file, 'w') as f:
        json.dump(assets, f, indent=4)


def add_downloaded_asset(asset_uid, asset_name, asset_type, asset_path, asset_import_size, thumbnail_image):
    """Add a new downloaded asset to the JSON file."""
    assets = load_downloaded_assets()
    assets[asset_uid] = {
        "asset_name": asset_name,
        "asset_type": asset_type,
        "asset_path": asset_path,
        "asset_import_size": asset_import_size,
        "thumbnail_image": thumbnail_image,
        "timestamp": datetime.now().isoformat()
    }
    save_downloaded_assets(assets)


def filter_downloaded_assets(assets, asset_type, import_size):
    """Filter downloaded assets based on type and import size."""
    filtered_assets = {}
    for uid, asset_data in assets.items():
        if asset_data["asset_type"] == asset_type and str(asset_data["asset_import_size"]) == import_size:
            filtered_assets[uid] = asset_data
    return filtered_assets


def update_assets(context, cursor):
    global loading_thread

    asset_type = str(context.scene.asset_type).strip()
    print(asset_type)
    query = context.scene.asset_search.strip()
    file_path = os.path.join(json_dir, f"search_{asset_type}_{query}_{cursor}.json")

    if os.path.exists(file_path):
        time_difference = datetime.now() - datetime.fromtimestamp(os.path.getmtime(file_path))
        print(f"last synced: {time_difference}")

    if not os.path.exists(file_path) or time_difference > timedelta(hours=5):
        url = "https://www.fab.com/i/listings/search"
        referer = "https://www.fab.com/sellers/Quixel"

        command = [python_path, utils_path, "--function", "fetch_assets", url, referer, json_dir, asset_type, query, cursor,]
        print(f"Running {command} inside the virtual environment...")
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        print(process.communicate()[0])

    loading_thread = threading.Thread(target=load_assets_in_background, args=(file_path,asset_type,))
    loading_thread.start()

    # Start UI timer to process the queue
    bpy.app.timers.register(update_ui_from_queue)


def load_assets_in_background(file_path,asset_type):
    global cancel_loading, asset_queue

    with open(file_path, 'r') as f:
        data = json.load(f)

    cursor_data = data.get("cursors", {})
    cursors["next_cursor"] = cursor_data.get("next")

    results_data = data.get("results", [])

    for item in results_data:
        if cancel_loading:
            print("Loading cancelled.")
            return  # Stop loading immediately
        asset_category = item["category"]["name"]
        if asset_category == "Plants":
            continue
        asset_name = item.get("title", "")
        uid = item.get("uid", "")
        img_path = preview_img  # Set temporary placeholder

        asset_queue.put((asset_name, uid, img_path))

    bpy.app.timers.register(update_ui_from_queue)

    for item in results_data:
        if cancel_loading:
            print("Loading cancelled.")
            return  # Stop loading immediately
        asset_category = item["category"]["name"]
        if asset_category == "Plants":
            continue
        asset_name = item.get("title", "")
        uid = item.get("uid", "")
        # img_url = item["thumbnails"][0]["mediaUrl"]
        img_url = next((img["url"] for img in item["thumbnails"][0]["images"] if img["height"] == 180), None)
        # img_name = item["thumbnails"][0]["name"]
        # Determine the image path
        img_name = os.path.basename(img_url) if img_url else None
        img_path = os.path.join(thumbnail_dir, img_name) if img_name else preview_img

        if os.path.exists(img_path):
            time_difference = datetime.now() - datetime.fromtimestamp(os.path.getmtime(img_path))

        if not os.path.exists(img_path) or time_difference > timedelta(days=5):
            if img_url:
                command = [python_path, utils_path, "--function", "download_file", img_url, img_path]
                print(f"Running {command} inside the virtual environment...")
                process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                process.communicate()

                if asset_type in ('material', 'decal'):
                    command = [python_path, utils_path, "--function", "crop_thumbnails", img_path,]
                    print(f"Running {command} inside the virtual environment...")
                    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                    print(process.communicate()[0])

                if asset_type == '3d-model':
                    command = [python_path, utils_path, "--function", "smart_square_crop", img_path, ]
                    print(f"Running {command} inside the virtual environment...")
                    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                    print(process.communicate()[0])

        if not os.path.exists(img_path):
            img_path = preview_img

        asset_queue.put((asset_name, uid, img_path))

    # Signal completion
    asset_queue.put(None)


def update_ui_from_queue():
    global asset_queue, preview_collection, cancel_loading

    while not asset_queue.empty():
        if cancel_loading:  # Exit early if loading is cancelled
            print("UI update cancelled.")
            return None

        item = asset_queue.get()

        if item is None:  # Stop signal
            print("Asset loading complete.")
            # bpy.context.window.cursor_set('DEFAULT')
            return None

        asset_name, uid, img_path = item

        if uid in preview_collection:
            del preview_collection[uid]
        preview_collection.load(uid, img_path, 'IMAGE')

        asset = preview_collection[uid]

        FILEBROWSER_PT_assets.assets[uid] = {"preview": asset, "img_path": img_path, "asset_name": asset_name}

        bpy.app.timers.register(force_ui_refresh, first_interval=0.01)

    return 0.1


def force_ui_refresh():
    """Force a UI refresh by tagging all areas for redraw."""
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            area.tag_redraw()
    return None  # Stop the timer


def import_to_scene(asset_name, asset_path, asset_type):
    print(asset_name)
    print(asset_path)

    if asset_path.endswith(".zip"):
        extract_path = os.path.join(unzipped_assets_dir, os.path.splitext(os.path.basename(asset_name))[0])
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

                    ass_name = os.path.splitext(os.path.basename(asset_name))[0]

                    # Create a collection for the asset
                    new_collection = bpy.data.collections.new(os.path.splitext(os.path.basename(ass_name))[0])
                    bpy.context.scene.collection.children.link(new_collection)

                    # Create a new empty object
                    new_empty = bpy.data.objects.new(ass_name, None)
                    new_collection.objects.link(new_empty)

                    bpy.ops.object.parent_clear(type='CLEAR_KEEP_TRANSFORM')

                    # Move imported objects to the new collection
                    for obj in bpy.context.selected_objects:
                        for collection in obj.users_collection:
                            collection.objects.unlink(obj)
                        new_collection.objects.link(obj)

                        if obj.type == 'MESH':
                            obj.parent = new_empty
                            material_name = obj.name + "_mat"
                            material = bpy.data.materials.get(material_name)
                            if not material:
                                material = bpy.data.materials.new(name=material_name)
                                create_pbr_shader(material, extract_path)
                            obj.data.materials.clear()
                            obj.data.materials.append(material)
                        else:
                            bpy.data.objects.remove(obj)
                    # Make the empty the active object and select it
                    bpy.context.view_layer.objects.active = new_empty
                    new_empty.select_set(True)
            return 0

        elif asset_type == 'material' or asset_type == 'decal':
            ass_name = os.path.splitext(os.path.basename(asset_name))[0]
            active_object = bpy.context.active_object
            if active_object is not None:
                print("Active Object Name:", active_object.name)
                if active_object.type == 'MESH':
                    material_name = ass_name + "_mat"
                    material = bpy.data.materials.get(material_name)
                    if not material:
                        material = bpy.data.materials.new(name=material_name)
                        create_pbr_shader(material, extract_path)
                    active_object.data.materials.clear()
                    active_object.data.materials.append(material)
                    return 0
                else:
                    print("Select a mesh object.")
                    return 1
            else:
                print("Select a mesh object.")
                return 1
    return 1


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
    principled_bsdf.location = (100, 0)

    # Create Material Output node
    material_output = nodes.new(type='ShaderNodeOutputMaterial')
    material_output.location = (400, 0)

    # Link the Principled BSDF to the Material Output
    links.new(principled_bsdf.outputs['BSDF'], material_output.inputs['Surface'])

    # Create Texture Coordinate node
    tex_coord_node = nodes.new(type='ShaderNodeTexCoord')
    tex_coord_node.location = (-1200, 0)

    # Create Mapping node
    mapping_node = nodes.new(type='ShaderNodeMapping')
    mapping_node.location = (-1000, 0)

    # Link Texture Coordinate to Mapping
    links.new(tex_coord_node.outputs['UV'], mapping_node.inputs['Vector'])

    # Define texture map keywords
    texture_map_keywords = {
        'Base Color': 'BaseColor',
        'Metallic': 'Metalness',
        'Normal': 'Normal',
        'Roughness': 'Roughness',
        'Specular': 'Specular',
        'AO': 'AO',
        'Bump': 'Bump',
        'Opacity': 'Opacity',
        'Displacement': 'Displacement'
    }

    # Get all jpg files in the specified directory
    texture_files = [f for f in os.listdir(texture_maps_path) if f.endswith('.jpg')]

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
            if map_type in ['Roughness', 'Metallic', 'Normal', 'Specular', 'AO', 'Bump', 'Opacity', 'Displacement']:
                image.colorspace_settings.name = 'Non-Color'

            texture_nodes[map_type] = image_texture

            # Connect Mapping node to each texture's vector input
            links.new(mapping_node.outputs['Vector'], image_texture.inputs['Vector'])

    # Connect Base Color and AO
    if 'Base Color' in texture_nodes:
        if 'AO' in texture_nodes:
            mix_rgb = nodes.new(type='ShaderNodeMixRGB')
            mix_rgb.blend_type = 'MULTIPLY'
            mix_rgb.location = (-200, 0)
            links.new(texture_nodes['Base Color'].outputs['Color'], mix_rgb.inputs[1])
            links.new(texture_nodes['AO'].outputs['Color'], mix_rgb.inputs[2])
            links.new(mix_rgb.outputs['Color'], principled_bsdf.inputs['Base Color'])
        else:
            links.new(texture_nodes['Base Color'].outputs['Color'], principled_bsdf.inputs['Base Color'])

    # Connect Roughness
    if 'Roughness' in texture_nodes:
        links.new(texture_nodes['Roughness'].outputs['Color'], principled_bsdf.inputs['Roughness'])

    # Connect Metallic
    if 'Metallic' in texture_nodes:
        links.new(texture_nodes['Metallic'].outputs['Color'], principled_bsdf.inputs['Metallic'])

    # Connect Specular
    if 'Specular' in texture_nodes:
        links.new(texture_nodes['Specular'].outputs['Color'], principled_bsdf.inputs['Specular IOR Level'])

    # Connect Opacity
    if 'Opacity' in texture_nodes:
        links.new(texture_nodes['Opacity'].outputs['Color'], principled_bsdf.inputs['Alpha'])

    # Connect Displacement
    if 'Displacement' in texture_nodes:
        displacement_node = nodes.new(type='ShaderNodeDisplacement')
        displacement_node.location = (100, -400)
        links.new(texture_nodes['Displacement'].outputs['Color'], displacement_node.inputs['Height'])
        links.new(displacement_node.outputs['Displacement'], material_output.inputs['Displacement'])

    # Connect Normal and Bump
    if 'Normal' in texture_nodes:
        if 'Bump' in texture_nodes:
            bump_node = nodes.new(type='ShaderNodeBump')
            bump_node.inputs['Strength'].default_value = 0.1
            bump_node.inputs['Distance'].default_value = 0.1
            bump_node.location = (-200, -200)
            links.new(texture_nodes['Bump'].outputs['Color'], bump_node.inputs['Height'])
            links.new(texture_nodes['Normal'].outputs['Color'], normal_map.inputs['Color'])
            links.new(normal_map.outputs['Normal'], bump_node.inputs['Normal'])
            links.new(bump_node.outputs['Normal'], principled_bsdf.inputs['Normal'])
        else:
            links.new(texture_nodes['Normal'].outputs['Color'], normal_map.inputs['Color'])
            links.new(normal_map.outputs['Normal'], principled_bsdf.inputs['Normal'])


def update_ui_with_progress(process):
    wm = bpy.context.window_manager
    wm.progress_begin(0, 100)

    try:
        for line in iter(process.stdout.readline, ''):
            if "Download Progress" in line:
                progress = float(line.split("Download Progress:")[1].strip().replace('%', ''))
                print(f"\rDownloading... {progress:.2f}%", end='')
                wm.progress_update(progress)
    except Exception as e:
        print(f"Error updating progress: {e}")
    finally:
        wm.progress_end()


### Operators and Properties ###

class FILEBROWSER_PT_assets(bpy.types.Panel):
    bl_label = "Quixel Assets"
    bl_idname = "FILEBROWSER_PT_assets"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'Quixel'

    assets = {}

    def draw(self, context):
        layout = self.layout
        layout.alignment = "CENTER"

        row = layout.row(align=True)
        row.operator("filebrowser.set_asset_mode", text="Online", depress=context.scene.asset_mode == 'online').asset_mode = 'online'
        row.operator("filebrowser.set_asset_mode", text="Downloaded", depress=context.scene.asset_mode == 'downloaded').asset_mode = 'downloaded'

        if context.scene.asset_mode == 'online':
            box = layout.box()
            row = box.row(align=True)
            row.operator("filebrowser.set_asset_type", text="3D Model", depress=context.scene.asset_type == '3d-model').asset_type = '3d-model'
            row.operator("filebrowser.set_asset_type", text="Material", depress=context.scene.asset_type == 'material').asset_type = 'material'
            row.operator("filebrowser.set_asset_type", text="Decal", depress=context.scene.asset_type == 'decal').asset_type = 'decal'

            row = box.row(align=True)
            row.operator("filebrowser.set_import_size", text="raw", depress=context.scene.import_size == '0').import_size = '0'
            row.operator("filebrowser.set_import_size", text="high", depress=context.scene.import_size == '1').import_size = '1'
            row.operator("filebrowser.set_import_size", text="mid", depress=context.scene.import_size == '2').import_size = '2'
            row.operator("filebrowser.set_import_size", text="low", depress=context.scene.import_size == '3').import_size = '3'

            row = box.row(align=True)
            row.operator("filebrowser.set_import_type", text="Import To Scene", depress=context.scene.import_type == 'import_to_scene').import_type = 'import_to_scene'
            row.operator("filebrowser.set_import_type", text="Add To Assets", depress=context.scene.import_type == 'add_to_asset_library').import_type = 'add_to_asset_library'

            # Search box and search button
            row = box.row(align=True)
            row.prop(context.scene, "asset_search", text="")
            row.operator("filebrowser.search_assets", text="", icon='VIEWZOOM')

            if self.assets:
                if cancel_loading:
                    print("Loading cancelled.")
                    layout.label(text="Loading Cancelled.")
                    return
                if len(self.assets) == 0:
                    layout.label(text="No assets available. Try searching or refreshing.")
                else:
                    row = box.row(align=True)
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

                        if preview:
                            asset_box.template_icon(preview.icon_id, scale=5)

                        # Add Import Button
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
            downloaded_assets = load_downloaded_assets()

            # Filter assets based on selected type and import size
            asset_type = context.scene.downloaded_asset_type
            import_size = context.scene.downloaded_import_size
            filtered_assets = filter_downloaded_assets(downloaded_assets, asset_type, import_size)

            # Add asset type selection buttons
            row = box.row(align=True)
            row.operator("filebrowser.set_downloaded_asset_type", text="3D Model", depress=asset_type == '3d-model').asset_type = '3d-model'
            row.operator("filebrowser.set_downloaded_asset_type", text="Material", depress=asset_type == 'material').asset_type = 'material'
            row.operator("filebrowser.set_downloaded_asset_type", text="Decal", depress=asset_type == 'decal').asset_type = 'decal'

            # Add import size selection buttons
            row = box.row(align=True)
            row.operator("filebrowser.set_downloaded_import_size", text="raw", depress=import_size == '0').import_size = '0'
            row.operator("filebrowser.set_downloaded_import_size", text="high", depress=import_size == '1').import_size = '1'
            row.operator("filebrowser.set_downloaded_import_size", text="mid", depress=import_size == '2').import_size = '2'
            row.operator("filebrowser.set_downloaded_import_size", text="low", depress=import_size == '3').import_size = '3'

            # Add import method selection buttons
            row = box.row(align=True)
            row.operator("filebrowser.set_downloaded_import_method", text="Import To Scene", depress=context.scene.downloaded_import_method == 'import_to_scene').import_method = 'import_to_scene'
            row.operator("filebrowser.set_downloaded_import_method", text="Add To Assets", depress=context.scene.downloaded_import_method == 'add_to_asset_library').import_method = 'add_to_asset_library'

            if filtered_assets:
                row = box.row(align=True)
                # Calculate the number of columns based on the panel's width
                min_width = 120  # Minimum width for a single column
                columns_count = max(1, min(int(context.region.width / min_width), len(filtered_assets)))
                column_list = [row.column(align=True) for _ in range(columns_count)]

                for i, (uid, asset_data) in enumerate(filtered_assets.items()):
                    col = column_list[i % columns_count]
                    asset_box = col.box()
                    asset_box.scale_x = 1.0
                    asset_box.scale_y = 1.0

                    # Load the thumbnail
                    thumbnail_path = asset_data["thumbnail_image"]
                    if os.path.exists(thumbnail_path):
                        preview = preview_collection.get(uid)
                        if not preview:
                            preview_collection.load(uid, thumbnail_path, 'IMAGE')
                        preview = preview_collection[uid]
                        asset_box.template_icon(preview.icon_id, scale=5)

                    # Add Import Button
                    import_btn = asset_box.operator("import_downloaded_asset.import", text=asset_data["asset_name"], icon="IMPORT")
                    import_btn.asset_uid = uid
                    import_btn.asset_name = os.path.basename(asset_data["asset_path"])
                    import_btn.asset_type = asset_data["asset_type"]
                    import_btn.asset_path = asset_data["asset_path"]
                    import_btn.thumbnail_path = thumbnail_path
                    import_btn.import_method = context.scene.downloaded_import_method
            else:
                box.label(text="No downloaded assets found.")


class IMPORT_ASSET_OT_import_asset(bpy.types.Operator):
    """Import Asset"""
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

        asset_type = str(context.scene.asset_type).strip()
        asset_formats_file = os.path.join(json_dir, f"asset_{self.uid}.json")

        if not os.path.exists(asset_formats_file):
            url = f"https://www.fab.com/i/listings/{self.uid}/asset-formats"
            referer = "https://www.fab.com/sellers/Quixel"

            command = [python_path, utils_path, "--function", "fetch_asset_formats", url, referer, json_dir, self.uid]
            print(f"Running {command} inside the virtual environment...")
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            print(process.communicate()[0])

        with open(asset_formats_file, "r") as f:
            data = json.load(f)
        asset_name = None
        asset_uid = None

        asset_format = None
        if asset_type == '3d-model':
            asset_format = "fbx"
        if asset_type == "material":
            asset_format = "texture-set"
        if asset_type == "decal":
            asset_format = "texture-set"

        if asset_format:
            import_size = int(context.scene.import_size.strip())
            for asset in data:
                if asset["assetFormatType"]["code"] == asset_format:
                    # asset_name = asset["files"][import_size]["name"]
                    while import_size >= 0:
                        try:
                            asset_name = asset["files"][import_size]["name"]
                            break
                        except IndexError:
                            import_size -= 1
                    asset_uid = asset["files"][import_size]["uid"]  # Get UID of last file
            print(f"UID for {asset_format}: {asset_uid}")

            asset_path = os.path.join(assets_dir, asset_name)

            if not os.path.exists(asset_path):
                down_link_file = os.path.join(json_dir, f"downlink_{asset_uid}.json")
                link_expired = True

                if os.path.exists(down_link_file):
                    with open(down_link_file, "r") as f:
                        data = json.load(f)
                    expires_dt = datetime.fromisoformat(data["downloadInfo"][0]["expires"].rstrip("Z")).replace(tzinfo=timezone.utc)
                    link_expired = datetime.now(timezone.utc) > expires_dt

                if link_expired:
                    url = f"https://www.fab.com/i/listings/{self.uid}/asset-formats/{asset_format}/files/{asset_uid}/download-info/binary"
                    referer = f"https://www.fab.com/i/listings/{self.uid}"

                    command = [python_path, utils_path, "--function", "fetch_down_link", url, referer, json_dir, asset_uid]
                    print(f"Running {command} inside the virtual environment...")
                    process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                    print(process.communicate()[0])

                with open(down_link_file, "r") as f:
                    data = json.load(f)
                    down_link = data["downloadInfo"][0]["downloadUrl"]

                command = [python_path, utils_path, "--function", "download_file", down_link, asset_path]
                print(f"Running {command} inside the virtual environment...")
                process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                # print(process.communicate()[0])
                progress_thread = threading.Thread(target=update_ui_with_progress, args=(process,))
                progress_thread.start()
                progress_thread.join()
                print('\n')

            # Add the downloaded asset to the JSON file
            add_downloaded_asset(asset_uid, self.asset_name, asset_type, asset_path, import_size, self.img_path)

            if context.scene.import_type == "import_to_scene":
                import_result = import_to_scene(asset_name, asset_path, asset_type)
                if import_result != 0:
                    self.report({'INFO'}, "Asset Import Failed")
                    return {'FINISHED'}

            elif context.scene.import_type == "add_to_asset_library":
                prefs = context.preferences.addons[__name__].preferences
                blender_path = prefs.blender_executable_path
                if not blender_path or not os.path.isfile(blender_path):
                    self.report({"ERROR"}, "Invalid Blender executable path!")
                    return {'CANCELLED'}
                command = [blender_path, "-b", "--factory-startup", "-P", asset_importer_path, "--", assets_dir, asset_name, asset_path, asset_type, self.img_path]
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
        if self.import_method == "import_to_scene":
            import_result = import_to_scene(self.asset_name, self.asset_path, self.asset_type)
            if import_result != 0:
                self.report({'INFO'}, "Asset Import Failed")
                return {'FINISHED'}
        elif self.import_method == "add_to_asset_library":
            prefs = context.preferences.addons[__name__].preferences
            blender_path = prefs.blender_executable_path
            if not blender_path or not os.path.isfile(blender_path):
                self.report({"ERROR"}, "Invalid Blender executable path!")
                return {'CANCELLED'}
            command = [blender_path, "-b", "--factory-startup", "-P", asset_importer_path, "--", assets_dir,
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
        global loading_thread, preview_collection, asset_queue, cancel_loading

        cancel_loading = True
        if loading_thread and loading_thread.is_alive():
            loading_thread.join()  # Wait for the thread to stop
            print("Stopping existing loading thread...")
        cancel_loading = False

        with asset_queue.mutex:  # Ensure thread-safe access to the queue
            asset_queue.queue.clear()

        if preview_collection:
            preview_collection.clear()
        FILEBROWSER_PT_assets.assets = {}

        # bpy.context.window.cursor_set('WAIT')
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
        global cancel_loading, loading_thread

        cancel_loading = True
        if loading_thread and loading_thread.is_alive():
            loading_thread.join()  # Wait for it to stop
        cancel_loading = False

        if cursors["next_cursor"] is not None:
            # bpy.context.window.cursor_set('WAIT')
            cursors["curr_cursor"] = cursors["next_cursor"]
            self.report({'INFO'}, "Loading more assets")
            update_assets(context, cursors["curr_cursor"])
        else:
            self.report({'INFO'}, "No more assets to load")
        return {'FINISHED'}


class FILEBROWSER_OT_set_asset_mode(bpy.types.Operator):
    bl_idname = "filebrowser.set_asset_mode"
    bl_label = "Set Asset Mode"

    asset_mode: bpy.props.StringProperty()

    def execute(self, context):
        if self.asset_mode == "downloaded":
            global loading_thread, preview_collection, asset_queue, cancel_loading

            cancel_loading = True
            if loading_thread and loading_thread.is_alive():
                loading_thread.join()  # Wait for the thread to stop
                print("Stopping existing loading thread...")
            cancel_loading = False

            with asset_queue.mutex:  # Ensure thread-safe access to the queue
                asset_queue.queue.clear()

            if preview_collection:
                preview_collection.clear()
            FILEBROWSER_PT_assets.assets = {}

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


classes = [
    FILEBROWSER_PT_assets,
    FILEBROWSER_OT_load_more,
    IMPORT_ASSET_OT_import_asset,
    FILEBROWSER_OT_search_assets,
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

    bpy.types.Scene.asset_search = bpy.props.StringProperty(
        name="Search Assets",
        update=FILEBROWSER_OT_search_assets.execute
    )

    bpy.types.Scene.asset_mode = bpy.props.StringProperty(
        name="Asset Mode",
        default='online'
    )

    bpy.types.Scene.asset_type = bpy.props.StringProperty(
        name="Asset Type",
        default='3d-model'
    )

    bpy.types.Scene.import_type = bpy.props.StringProperty(
        name="Import Type",
        default='import_to_scene'
    )

    bpy.types.Scene.import_size = bpy.props.StringProperty(
        name="Import Size",
        default='2'
    )

    bpy.types.Scene.downloaded_asset_type = bpy.props.StringProperty(
        name="Downloaded Asset Type",
        default="3d-model"
    )

    bpy.types.Scene.downloaded_import_size = bpy.props.StringProperty(
        name="Downloaded Import Size",
        default="2"
    )

    bpy.types.Scene.downloaded_import_method = bpy.props.StringProperty(
        name="Downloaded Import Method",
        default="import_to_scene"
    )

    FILEBROWSER_PT_assets.assets = {}
    initialize_paths()
    setup_env()
    initialize_preview_collection()
    fix_asset_paths()
    # clear_thumbnail_cache()


def unregister():
    for cls in reversed(classes):
        bpy.utils.unregister_class(cls)

    del bpy.types.Scene.asset_search
    del bpy.types.Scene.asset_mode
    del bpy.types.Scene.asset_type
    del bpy.types.Scene.import_type
    del bpy.types.Scene.import_size

    cleanup_preview_collection()


if __name__ == "__main__":
    register()

