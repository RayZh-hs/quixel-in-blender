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
import concurrent.futures

bl_info = {
    "name": "Fab to Blender",
    "description": "Browse and import free quixel assets from fab.com",
    "author": "https://github.com/cgmaterial",
    "version": (2, 1, 0),
    "blender": (4, 4, 3),
    "location": "View3D > Sidebar > Quixel",
    "category": "Asset Management",
}

# Paths relative to the addon directory
current_file_dir = os.path.dirname(__file__)
utils_path = os.path.join(current_file_dir, "tools", "utils.py")
asset_importer_path = os.path.join(current_file_dir, "tools", "asset_importer.py")
preview_img = os.path.join(current_file_dir, "images", "preview.svg")

# Blender executable path
def_blender_executable_path = bpy.app.binary_path

# Default asset data path
def_asset_data_path = os.path.join(os.getenv('USERPROFILE' if platform.system() == 'Windows' else 'HOME'), 'Documents')

# Default system Python detection
try:
    def_system_python = subprocess.check_output(
        ['where' if platform.system() == 'Windows' else 'which', 'python3']).strip().decode('utf-8')
except:
    def_system_python = ""

# Asset library and other variables
asset_lib_name = "Quixel Assets"
asset_queue = queue.Queue()
loading_thread = None
cursors = {"curr_cursor": "0", "next_cursor": "0"}
preview_collection = None
cancel_loading = False


def get_asset_paths(context):
    """Generate all asset-related paths based on the addon's preferences."""
    prefs = context.preferences.addons[__name__].preferences
    asset_data_path = prefs.asset_data_path
    data_dir = os.path.join(asset_data_path, "fab_data")
    env_dir = os.path.join(asset_data_path, "fab-env")
    python_path = os.path.join(env_dir, "Scripts" if platform.system() == 'Windows' else "bin", "python")
    thumbnail_dir = os.path.join(data_dir, "thumbnails")
    assets_dir = os.path.join(data_dir, "quixel_assets")
    json_dir = os.path.join(data_dir, "json_files")
    unzipped_assets_dir = os.path.join(assets_dir, "unzipped_assets")
    blender_files_dir = os.path.join(assets_dir, "blender_files")
    catalog_file = os.path.join(assets_dir, "blender_assets.cats.txt")
    downloaded_assets_file = os.path.join(assets_dir, "downloaded_assets.json")
    return {
        "data_dir": data_dir,
        "env_dir": env_dir,
        "python_path": python_path,
        "thumbnail_dir": thumbnail_dir,
        "assets_dir": assets_dir,
        "json_dir": json_dir,
        "unzipped_assets_dir": unzipped_assets_dir,
        "blender_files_dir": blender_files_dir,
        "catalog_file": catalog_file,
        "downloaded_assets_file": downloaded_assets_file
    }


def get_thumbnail_cache_size(context):
    paths = get_asset_paths(context)
    thumbnail_dir = paths["thumbnail_dir"]
    total_size = 0
    for item in os.listdir(thumbnail_dir):
        thumbnail = os.path.join(thumbnail_dir, item)
        if os.path.isfile(thumbnail):
            total_size += os.path.getsize(thumbnail)
    return total_size / (1024 ** 2)


def get_jsonfile_cache_size(context):
    paths = get_asset_paths(context)
    json_dir = paths["json_dir"]
    total_size = 0
    for item in os.listdir(json_dir):
        json_file = os.path.join(json_dir, item)
        if os.path.isfile(json_file):
            total_size += os.path.getsize(json_file)
    return total_size / (1024 ** 2)


def get_zipfile_cache_size(context):
    paths = get_asset_paths(context)
    assets_dir = paths["assets_dir"]
    total_size = 0
    for item in os.listdir(assets_dir):
        if item.endswith(".zip"):
            zip_file = os.path.join(assets_dir, item)
            if os.path.isfile(zip_file):
                total_size += os.path.getsize(zip_file)
    return total_size / (1024 ** 2)


def is_valid_python_path(path):
    """Check if the provided path is a valid Python executable."""
    if not path or not os.path.isfile(path):
        return False
    try:
        result = subprocess.run(
            [path, "--version"], capture_output=True, text=True, timeout=5)
        return result.returncode == 0 and "Python" in result.stdout
    except (subprocess.SubprocessError, OSError):
        return False


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

    system_python: bpy.props.StringProperty(
        name="System Python Path",
        description="Path to the system Python executable",
        subtype='FILE_PATH',
        default=def_system_python,
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
        # thumbnail_size_mb = get_thumbnail_cache_size(context) / (1024 ** 2)
        row.label(text=f"Thumbnail Cache: {get_thumbnail_cache_size(context):.2f} MB")
        row.operator("filebrowser.clear_thumbnails", text="Clear Thumbnail Cache", icon='TRASH')
        row = layout.row()
        row.label(text=f"JSON Cache: {get_jsonfile_cache_size(context):.2f} MB")
        row.operator("filebrowser.clear_jsonfiles", text="Clear JSON Cache", icon='TRASH')
        row = layout.row()
        row.label(text=f"ZIP file Cache: {get_zipfile_cache_size(context):.2f} MB")
        row.operator("filebrowser.clear_zipfiles", text="Clear ZIP file Cache", icon='TRASH')
        layout.separator()
        row = layout.row()
        row.operator("wm.url_open", text="Report a Bug", icon='URL').url = "https://github.com/cgmaterial/fab-to-blender/issues/new"
        row.operator("wm.url_open", text="Support Development", icon='FUND').url = "https://ko-fi.com/cg_material"


def initialize_paths(context):
    """Initialize all directories and virtual environment based on preferences."""
    paths = get_asset_paths(context)

    # Create directories
    for path in [paths["data_dir"], paths["thumbnail_dir"],
                 paths["assets_dir"], paths["json_dir"], paths["unzipped_assets_dir"],
                 paths["blender_files_dir"]]:
        os.makedirs(path, exist_ok=True)

    # Initialize catalog file if it doesn't exist
    if not os.path.exists(paths["catalog_file"]):
        with open(paths["catalog_file"], 'w') as f:
            f.write(f"VERSION 1\n{str(uuid.uuid4())}:3d:3d\n{str(uuid.uuid4())}:surface:surface\n")

    # Add asset library if not already present
    asset_library_paths = [library.path for library in bpy.context.preferences.filepaths.asset_libraries]
    if paths["assets_dir"] not in asset_library_paths:
        bpy.app.timers.register(lambda: add_asset_library(paths["assets_dir"]), first_interval=1.0)


def update_asset_data_path(self, context):
    """Update paths and reinitialize directories when asset_data_path changes."""
    initialize_paths(context)
    setup_env(context)  # Reinitialize virtual environment if needed
    print("Updated asset data path and reinitialized directories.")


def setup_env(context):
    """Set up the virtual environment if it doesn't exist."""
    paths = get_asset_paths(context)
    system_python = context.preferences.addons[__name__].preferences.system_python
    if not is_valid_python_path(system_python):
        print(f"Error: Invalid or unset Python path: {system_python}. Skipping virtual environment setup.")
        return
    if not os.path.exists(paths["env_dir"]):
        print(f"Creating virtual environment at {paths['env_dir']}")
        subprocess.check_call([system_python, "-m", "venv", paths["env_dir"]])
        subprocess.check_call([paths["python_path"], "-m", "pip", "install", "--upgrade", "pip"])
        subprocess.check_call(
            [paths["python_path"], "-m", "pip", "install", "requests", "cloudscraper", "zstandard", "pillow"])


def add_asset_library(assets_dir):
    """Add the asset library to Blender's preferences."""
    try:
        bpy.ops.preferences.asset_library_add()
        asset_library = bpy.context.preferences.filepaths.asset_libraries[-1]
        asset_library.name = asset_lib_name
        asset_library.path = assets_dir
        print(f"Asset library added: {assets_dir}")
    except Exception as e:
        print(f"Failed to add asset library: {e}")
    return None


def initialize_preview_collection(context):
    global preview_collection
    paths = get_asset_paths(context)
    if not preview_collection:
        preview_collection = bpy.utils.previews.new()
        preview_collection.load("preview", preview_img, 'IMAGE')

    # Load thumbnails for downloaded assets
    downloaded_assets = load_downloaded_assets(context)
    for uid, asset_data in downloaded_assets.items():
        thumbnail_path = asset_data["thumbnail_image"]
        if os.path.exists(thumbnail_path):
            preview_collection.load(uid, thumbnail_path, 'IMAGE')


def cleanup_preview_collection():
    global preview_collection
    if preview_collection:
        bpy.utils.previews.remove(preview_collection)
        preview_collection = None


def fix_asset_paths(context):
    paths = get_asset_paths(context)
    for item in os.listdir(paths["unzipped_assets_dir"]):
        if item and os.path.isdir(os.path.join(paths["unzipped_assets_dir"], item)):
            if item.endswith(".zip"):
                new_name = item[:-4]
                old_path = os.path.join(paths["unzipped_assets_dir"], item)
                new_path = os.path.join(paths["unzipped_assets_dir"], new_name)
                os.rename(old_path, new_path)
                print(f"Renamed folder: {item} -> {new_name}")


def clear_thumbnail_cache(context):
    paths = get_asset_paths(context)
    thumbnail_dir = paths["thumbnail_dir"]
    deleted = 0
    size_freed = 0

    if not os.path.exists(thumbnail_dir):
        print("Thumbnail directory does not exist.")
        return

    for item in os.listdir(thumbnail_dir):
        thumbnail = os.path.join(thumbnail_dir, item)
        if os.path.isfile(thumbnail):
            try:
                size_freed += os.path.getsize(thumbnail)
                os.remove(thumbnail)
                deleted += 1
            except Exception as e:
                print(f"Failed to remove {thumbnail}: {e}")

    print(f"Cleared {deleted} thumbnails, freed {size_freed / (1024**2):.2f} MB")


def clear_jsonfile_cache(context):
    paths = get_asset_paths(context)
    json_dir = paths["json_dir"]
    deleted = 0
    size_freed = 0

    if not os.path.exists(json_dir):
        print("json directory does not exist.")
        return

    for item in os.listdir(json_dir):
        json_file = os.path.join(json_dir, item)
        if os.path.isfile(json_file):
            try:
                size_freed += os.path.getsize(json_file)
                os.remove(json_file)
                deleted += 1
            except Exception as e:
                print(f"Failed to delete {json_file}: {e}")

    print(f"Cleared {deleted} JSON files, freed {size_freed / (1024 ** 2):.2f} MB")


def clear_zipfile_cache(context):
    paths = get_asset_paths(context)
    assets_dir = paths["assets_dir"]
    deleted = 0
    size_freed = 0

    for item in os.listdir(assets_dir):
        if item.endswith(".zip"):
            zip_file = os.path.join(assets_dir, item)
            if os.path.isfile(zip_file):
                try:
                    size_freed += os.path.getsize(zip_file)
                    os.remove(zip_file)
                    deleted += 1
                except Exception as e:
                    print(f"Failed to delete {zip_file}: {e}")

    print(f"Deleted {deleted} ZIP files, freed {size_freed / (1024 ** 2):.2f} MB")


def load_downloaded_assets(context):
    """Load the downloaded assets from the JSON file."""
    paths = get_asset_paths(context)
    if os.path.exists(paths["downloaded_assets_file"]):
        with open(paths["downloaded_assets_file"], 'r') as f:
            return json.load(f)
    return {}


def save_downloaded_assets(context, assets):
    """Save the downloaded assets to the JSON file."""
    paths = get_asset_paths(context)
    with open(paths["downloaded_assets_file"], 'w') as f:
        json.dump(assets, f, indent=4)


def add_downloaded_asset(context, asset_uid, asset_name, asset_type, asset_path, asset_import_size, thumbnail_image):
    """Add a new downloaded asset to the JSON file."""
    assets = load_downloaded_assets(context)
    assets[asset_uid] = {
        "asset_name": asset_name,
        "asset_type": asset_type,
        "asset_path": asset_path,
        "asset_import_size": asset_import_size,
        "thumbnail_image": thumbnail_image,
        "timestamp": datetime.now().isoformat()
    }
    save_downloaded_assets(context, assets)


def filter_downloaded_assets(context, assets, asset_type, import_size):
    """Filter downloaded assets based on type and import size."""
    filtered_assets = {}
    for uid, asset_data in assets.items():
        if asset_data["asset_type"] == asset_type and str(asset_data["asset_import_size"]) == import_size:
            filtered_assets[uid] = asset_data
    return filtered_assets


def update_assets(context, cursor):
    global loading_thread
    paths = get_asset_paths(context)
    if not is_valid_python_path(context.preferences.addons[__name__].preferences.system_python):
        print("Cannot update assets: Invalid or unset Python path.")
        return
    asset_type = str(context.scene.asset_type).strip()
    query = context.scene.asset_search.strip()
    file_path = os.path.join(paths["json_dir"], f"search_{asset_type}_{query}_{cursor}.json")

    if os.path.exists(file_path):
        time_difference = datetime.now() - datetime.fromtimestamp(os.path.getmtime(file_path))
        print(f"last synced: {time_difference}")

    if not os.path.exists(file_path) or time_difference > timedelta(hours=5):
        url = "https://www.fab.com/i/listings/search"
        referer = "https://www.fab.com/sellers/Quixel"
        command = [paths["python_path"], utils_path, "--function", "fetch_assets", url, referer, paths["json_dir"],
                   asset_type, query, cursor]
        print(f"Running {command} inside the virtual environment...")
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        print(process.communicate()[0])

    loading_thread = threading.Thread(target=load_assets_in_background, args=(file_path, asset_type, context))
    loading_thread.start()
    bpy.app.timers.register(update_ui_from_queue)


def load_assets_in_background(file_path, asset_type, context):
    global cancel_loading, asset_queue
    paths = get_asset_paths(context)

    with open(file_path, 'r') as f:
        data = json.load(f)

    cursor_data = data.get("cursors", {})
    cursors["next_cursor"] = cursor_data.get("next")

    results_data = data.get("results", [])
    items_to_download = []

    for item in results_data:
        if cancel_loading:
            print("Loading cancelled.")
            return
        asset_category = item["category"]["name"]
        if asset_category == "Plants":
            continue
        asset_name = item.get("title", "")
        uid = item.get("uid", "")
        asset_queue.put((asset_name, uid, preview_img))  # Temporary placeholder

        # Prepare download
        img_url = preview_img  # fallback image
        images = item.get("thumbnails", [{}])[0].get("images", [])
        if images:
            closest_img = min(images, key=lambda img: abs(img.get("height", 0) - 180))
            img_url = closest_img.get("url", preview_img)
        if img_url:
            img_name = os.path.basename(img_url)
            img_path = os.path.join(paths["thumbnail_dir"], img_name)
            items_to_download.append((asset_name, uid, img_url, img_path))

    bpy.app.timers.register(update_ui_from_queue)

    def download_and_process(item):
        asset_name, uid, img_url, img_path = item
        if os.path.exists(img_path):
            time_diff = datetime.now() - datetime.fromtimestamp(os.path.getmtime(img_path))
            if time_diff <= timedelta(days=5):
                return (asset_name, uid, img_path)

        try:
            subprocess.run([paths["python_path"], utils_path, "--function", "download_file", img_url, img_path],
                           check=True, capture_output=True, text=True)
            if asset_type in ('material', 'decal'):
                subprocess.run([paths["python_path"], utils_path, "--function", "crop_thumbnails", img_path],
                               check=True, capture_output=True, text=True)
            elif asset_type == '3d-model':
                subprocess.run([paths["python_path"], utils_path, "--function", "smart_square_crop", img_path],
                               check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as e:
            print(f"Failed to download/process {uid}: {e}")

        if not os.path.exists(img_path):
            img_path = preview_img
        return (asset_name, uid, img_path)

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        for result in executor.map(download_and_process, items_to_download):
            if cancel_loading:
                print("Loading cancelled.")
                return
            asset_queue.put(result)

    asset_queue.put(None)


def update_ui_from_queue():
    global asset_queue, preview_collection, cancel_loading
    while not asset_queue.empty():
        if cancel_loading:
            print("UI update cancelled.")
            return None
        item = asset_queue.get()
        if item is None:
            print("Asset loading complete.")
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
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            area.tag_redraw()
    return None


def import_to_scene(context, asset_name, asset_path, asset_type):
    paths = get_asset_paths(context)
    print(asset_name)
    print(asset_path)

    if asset_path.endswith(".zip"):
        extract_name = os.path.splitext(os.path.basename(asset_name))[0]
        extract_path = os.path.join(paths["unzipped_assets_dir"], extract_name)

        if os.path.exists(extract_path):
            print(f"Using extracted folder: {extract_path}")
        elif os.path.exists(asset_path):
            print(f"Extracting from ZIP: {asset_path}")
            try:
                with zipfile.ZipFile(asset_path, 'r') as zip_ref:
                    zip_ref.extractall(extract_path)
                print(f"Extracted {asset_name} to {extract_path}")
            except zipfile.BadZipFile:
                print(f"{asset_name} is not a valid ZIP file.")
                return 1
        else:
            print(f"Missing both ZIP and extracted folder for asset: {asset_name}")
            return 1

        if asset_type == '3d-model':
            for file_name in os.listdir(extract_path):
                if file_name.endswith(".fbx"):
                    fbx_path = os.path.join(extract_path, file_name)
                    bpy.ops.import_scene.fbx(filepath=fbx_path)
                    print(f"Imported FBX: {fbx_path}")
                    ass_name = os.path.splitext(os.path.basename(asset_name))[0]
                    new_collection = bpy.data.collections.new(ass_name)
                    bpy.context.scene.collection.children.link(new_collection)
                    new_empty = bpy.data.objects.new(ass_name, None)
                    new_collection.objects.link(new_empty)
                    bpy.ops.object.parent_clear(type='CLEAR_KEEP_TRANSFORM')
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
                    bpy.context.view_layer.objects.active = new_empty
                    new_empty.select_set(True)
            return 0

        elif asset_type in ('material', 'decal'):
            ass_name = os.path.splitext(os.path.basename(asset_name))[0]
            active_object = bpy.context.active_object
            if active_object and active_object.type == 'MESH':
                print("Active Object Name:", active_object.name)
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
                    min_width = 120
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
                        preview = preview_collection.get(uid)
                        if not preview:
                            preview_collection.load(uid, thumbnail_path, 'IMAGE')
                        preview = preview_collection[uid]
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
        if not is_valid_python_path(context.preferences.addons[__name__].preferences.system_python):
            self.report({'ERROR'}, "Invalid or unset Python path. Please set a valid Python executable in preferences.")
            bpy.context.window.cursor_set('DEFAULT')
            return {'CANCELLED'}
        asset_type = str(context.scene.asset_type).strip()
        asset_formats_file = os.path.join(paths["json_dir"], f"asset_{self.uid}.json")

        if not os.path.exists(asset_formats_file):
            url = f"https://www.fab.com/i/listings/{self.uid}/asset-formats"
            referer = "https://www.fab.com/sellers/Quixel"
            command = [paths["python_path"], utils_path, "--function", "fetch_asset_formats", url, referer,
                       paths["json_dir"], self.uid]
            print(f"Running {command} inside the virtual environment...")
            process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            print(process.communicate()[0])

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
                        url = f"https://www.fab.com/i/listings/{self.uid}/asset-formats/{asset_format}/files/{asset_uid}/download-info/binary"
                        referer = f"https://www.fab.com/i/listings/{self.uid}"
                        command = [paths["python_path"], utils_path, "--function", "fetch_down_link", url, referer,
                                   paths["json_dir"], asset_uid]
                        print(f"Running {command} inside the virtual environment...")
                        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                        print(process.communicate()[0])
                    with open(down_link_file, "r") as f:
                        data = json.load(f)
                        down_link = data["downloadInfo"][0]["downloadUrl"]
                    command = [paths["python_path"], utils_path, "--function", "download_file", down_link, asset_path]
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
                prefs = context.preferences.addons[__name__].preferences
                blender_path = prefs.blender_executable_path
                if not blender_path or not os.path.isfile(blender_path):
                    self.report({"ERROR"}, "Invalid Blender executable path!")
                    return {'CANCELLED'}
                command = [blender_path, "-b", "--factory-startup", "-P", asset_importer_path, "--",
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
            prefs = context.preferences.addons[__name__].preferences
            blender_path = prefs.blender_executable_path
            if not blender_path or not os.path.isfile(blender_path):
                self.report({"ERROR"}, "Invalid Blender executable path!")
                return {'CANCELLED'}
            command = [blender_path, "-b", "--factory-startup", "-P", asset_importer_path, "--", paths["assets_dir"],
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
            loading_thread.join()
            print("Stopping existing loading thread...")
        cancel_loading = False
        with asset_queue.mutex:
            asset_queue.queue.clear()
        if preview_collection:
            preview_collection.clear()
        FILEBROWSER_PT_assets.assets = {}
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
            loading_thread.join()
        cancel_loading = False
        if cursors["next_cursor"] is not None:
            cursors["curr_cursor"] = cursors["next_cursor"]
            self.report({'INFO'}, "Loading more assets")
            update_assets(context, cursors["curr_cursor"])
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


class FILEBROWSER_OT_set_asset_mode(bpy.types.Operator):
    bl_idname = "filebrowser.set_asset_mode"
    bl_label = "Set Asset Mode"
    asset_mode: bpy.props.StringProperty()

    def execute(self, context):
        if self.asset_mode == "downloaded":
            global loading_thread, preview_collection, asset_queue, cancel_loading
            cancel_loading = True
            if loading_thread and loading_thread.is_alive():
                loading_thread.join()
                print("Stopping existing loading thread...")
            cancel_loading = False
            with asset_queue.mutex:
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
    FILEBROWSER_OT_clear_thumbnails,
    FILEBROWSER_OT_clear_jsonfiles,
    FILEBROWSER_OT_clear_zipfiles,
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
    initialize_paths(bpy.context)
    setup_env(bpy.context)
    initialize_preview_collection(bpy.context)
    fix_asset_paths(bpy.context)


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