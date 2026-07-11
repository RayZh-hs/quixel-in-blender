"""Filesystem layout, virtual environment, and cache management.

Everything here is about the addon's on-disk data directory (derived from the
``asset_data_path`` preference): computing the set of paths it uses, creating those
directories, building the isolated Python venv that ``scripts/fab_api.py`` runs in,
registering the Blender asset library, and clearing the various caches.

Depends only on :mod:`.constants`.
"""

import os
import platform
import shutil
import subprocess
import uuid

import bpy

from .constants import ADDON_ID, ASSET_LIB_NAME


def get_asset_paths(context):
    """Generate all asset-related paths based on the addon's preferences."""
    prefs = context.preferences.addons[ADDON_ID].preferences
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


def setup_env(context, reset=False):
    """Set up the virtual environment if it doesn't exist."""
    paths = get_asset_paths(context)
    system_python = context.preferences.addons[ADDON_ID].preferences.system_python
    if not is_valid_python_path(system_python):
        print(f"Error: Invalid or unset Python path: {system_python}. Skipping virtual environment setup.")
        return

    if reset and os.path.exists(paths["env_dir"]):
        print(f"Resetting virtual environment at {paths['env_dir']}")
        shutil.rmtree(paths["env_dir"], ignore_errors=True)

    if not os.path.exists(paths["env_dir"]):
        print(f"Creating virtual environment at {paths['env_dir']}")
        subprocess.check_call([system_python, "-m", "venv", paths["env_dir"]])
        subprocess.check_call([paths["python_path"], "-m", "pip", "install", "--upgrade", "pip"])
        subprocess.check_call(
            [paths["python_path"], "-m", "pip", "install", "requests", "cloudscraper", "zstandard", "pillow", "pycookiecheat"])


def add_asset_library(assets_dir):
    """Add the asset library to Blender's preferences."""
    try:
        bpy.ops.preferences.asset_library_add()
        asset_library = bpy.context.preferences.filepaths.asset_libraries[-1]
        asset_library.name = ASSET_LIB_NAME
        asset_library.path = assets_dir
        print(f"Asset library added: {assets_dir}")
    except Exception as e:
        print(f"Failed to add asset library: {e}")
    return None


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
