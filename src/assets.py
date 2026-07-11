"""Asset search, background loading, and the downloaded-asset store.

Two responsibilities:

* **Downloaded-asset store** — a small JSON database (``downloaded_assets.json``)
  recording what has been downloaded, used to populate the "Downloaded" tab.
* **Online search pipeline** — kicks off ``scripts/fab_api.py`` (in the venv) to
  fetch a listings page, then streams the results into the UI on a background
  thread: thumbnails are downloaded/cropped in a thread pool and pushed onto
  :data:`state.asset_queue`, which a Blender timer (:func:`update_ui_from_queue`)
  drains into :data:`state.assets` and the preview collection.

Shared runtime state (queue, cursors, cancel flag, preview collection, the visible
``assets`` dict) lives in :mod:`.state`; see that module for the mutation rules.

Depends on :mod:`.constants`, :mod:`.state`, :mod:`.paths` and :mod:`.importer`.
"""

import concurrent.futures
import json
import os
import subprocess
import threading
from datetime import datetime, timedelta

import bpy

from . import state
from .constants import ADDON_ID, FAB_API_SCRIPT, PREVIEW_IMG
from .paths import get_asset_paths, is_valid_python_path


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
    paths = get_asset_paths(context)
    if not is_valid_python_path(context.preferences.addons[ADDON_ID].preferences.system_python):
        print("Cannot update assets: Invalid or unset Python path.")
        return
    asset_type = str(context.scene.asset_type).strip()
    query = context.scene.asset_search.strip()
    sort_method = context.scene.sort_method
    file_path = os.path.join(paths["json_dir"], f"search_{asset_type}_{query}_{sort_method}_{cursor}.json")

    if os.path.exists(file_path):
        time_difference = datetime.now() - datetime.fromtimestamp(os.path.getmtime(file_path))
        print(f"last synced: {time_difference}")

    if not os.path.exists(file_path) or time_difference > timedelta(hours=5):
        url = "https://www.fab.com/i/listings/search"
        referer = "https://www.fab.com/sellers/Quixel%20Megascans"
        command = [paths["python_path"], FAB_API_SCRIPT, "--function", "fetch_assets", url, referer, paths["json_dir"],
                   asset_type, query, cursor, sort_method]
        print(f"Running {command} inside the virtual environment...")
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        print(process.communicate()[0])

    state.loading_thread = threading.Thread(target=load_assets_in_background, args=(file_path, asset_type, context))
    state.loading_thread.start()
    bpy.app.timers.register(update_ui_from_queue)


def load_assets_in_background(file_path, asset_type, context):
    paths = get_asset_paths(context)

    with open(file_path, 'r') as f:
        data = json.load(f)

    cursor_data = data.get("cursors", {})
    state.cursors["next_cursor"] = cursor_data.get("next")

    results_data = data.get("results", [])
    items_to_download = []

    for item in results_data:
        if state.cancel_loading:
            print("Loading cancelled.")
            return
        asset_category = item["category"]["name"]
        if asset_category == "Plants":
            continue
        asset_name = item.get("title", "")
        uid = item.get("uid", "")
        state.asset_queue.put((asset_name, uid, PREVIEW_IMG))  # Temporary placeholder

        # Prepare download
        img_url = PREVIEW_IMG  # fallback image
        images = item.get("thumbnails", [{}])[0].get("images", [])
        if images:
            closest_img = min(images, key=lambda img: abs(img.get("height", 0) - 180))
            img_url = closest_img.get("url", PREVIEW_IMG)
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
            subprocess.run([paths["python_path"], FAB_API_SCRIPT, "--function", "download_file", img_url, img_path],
                           check=True, capture_output=True, text=True)
            if asset_type in ('material', 'decal'):
                subprocess.run([paths["python_path"], FAB_API_SCRIPT, "--function", "crop_thumbnails", img_path],
                               check=True, capture_output=True, text=True)
            elif asset_type == '3d-model':
                subprocess.run([paths["python_path"], FAB_API_SCRIPT, "--function", "smart_square_crop", img_path],
                               check=True, capture_output=True, text=True)
        except subprocess.CalledProcessError as e:
            print(f"Failed to download/process {uid}: {e}")

        if not os.path.exists(img_path):
            img_path = PREVIEW_IMG
        return (asset_name, uid, img_path)

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        for result in executor.map(download_and_process, items_to_download):
            if state.cancel_loading:
                print("Loading cancelled.")
                return
            state.asset_queue.put(result)

    state.asset_queue.put(None)


def update_ui_from_queue():
    while not state.asset_queue.empty():
        if state.cancel_loading:
            print("UI update cancelled.")
            return None
        item = state.asset_queue.get()
        if item is None:
            print("Asset loading complete.")
            return None
        asset_name, uid, img_path = item
        if uid in state.preview_collection:
            del state.preview_collection[uid]
        state.preview_collection.load(uid, img_path, 'IMAGE')
        asset = state.preview_collection[uid]
        state.assets[uid] = {"preview": asset, "img_path": img_path, "asset_name": asset_name}
        bpy.app.timers.register(force_ui_refresh, first_interval=0.01)
    return 0.1


def force_ui_refresh():
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            area.tag_redraw()
    return None
