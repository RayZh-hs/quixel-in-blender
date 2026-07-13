"""Asset search, placeholder generation, the import core, and the downloaded store.

Responsibilities:

* **Downloaded-asset store** — a small JSON database (``downloaded_assets.json``)
  recording what has been downloaded.
* **Import core** — :func:`download_and_build_asset` resolves/downloads a Fab asset
  and either imports it into the scene or builds a library ``.blend`` out-of-process.
  Reused by the import operator and the drag-download handler.
* **Online search pipeline** — kicks off ``scripts/fab_api.py`` (in the venv) to
  fetch a listings page, then on a background thread downloads/crops thumbnails,
  accumulates a manifest into :data:`state.manifest`, and rebuilds the shared
  ``placeholders.blend`` (via ``scripts/placeholder_builder.py``) so results show up
  in the native Asset Browser. A main-thread timer then refreshes open browsers.

Shared runtime state (cursors, cancel flag, manifest) lives in :mod:`.state`.

Depends on :mod:`.constants`, :mod:`.state`, :mod:`.paths` and :mod:`.importer`.
"""

import concurrent.futures
import json
import os
import subprocess
import threading
from datetime import datetime, timedelta, timezone

import bpy

from . import state
from .constants import ADDON_ID, ASSET_IMPORTER_SCRIPT, FAB_API_SCRIPT, PLACEHOLDER_BUILDER_SCRIPT
from .paths import get_asset_paths, is_valid_python_path
from .importer import import_to_scene, update_ui_with_progress


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


def refresh_asset_browser():
    """Tell every open Asset Browser to re-scan the library (picks up new .blends).

    Scans all windows, not just the active screen, because the Quixel browser opens in
    its own window and may not be the active one when a background build finishes.
    """
    for win in bpy.context.window_manager.windows:
        for area in win.screen.areas:
            if area.type == 'FILE_BROWSER':
                with bpy.context.temp_override(window=win, area=area):
                    bpy.ops.asset.library_refresh()


def download_and_build_asset(context, uid, asset_type, size, import_type,
                             display_name=None, img_path=None):
    """Resolve, download and build one Fab asset.

    This is the shared import core extracted from :class:`operators.IMPORT_ASSET_OT_import_asset`
    so it can be reused by the drag-download handler without an operator context. It
    resolves the asset-formats JSON, picks the file for ``size`` (falling back to a
    smaller size on ``IndexError``), fetches/validates a download link, downloads the
    zip, records it in the downloaded-asset store, then either imports it into the
    scene or builds a library ``.blend`` out-of-process.

    ``import_type`` is ``'import_to_scene'`` or ``'add_to_asset_library'``.
    Returns ``(status, message)`` where ``status == 0`` means success.
    """
    paths = get_asset_paths(context)
    if not is_valid_python_path(context.preferences.addons[ADDON_ID].preferences.system_python):
        return 1, "Invalid or unset Python path. Please set a valid Python executable in preferences."

    asset_formats_file = os.path.join(paths["json_dir"], f"asset_{uid}.json")
    if not os.path.exists(asset_formats_file):
        url = f"https://www.fab.com/i/listings/{uid}/asset-formats"
        referer = f"https://www.fab.com/i/listings/{uid}"
        command = [paths["python_path"], FAB_API_SCRIPT, "--function", "fetch_asset_formats", url, referer,
                   paths["json_dir"], uid]
        print(f"Running {command} inside the virtual environment...")
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        print(process.communicate()[0])

    if not os.path.exists(asset_formats_file):
        return 1, ("Could not fetch asset formats from fab.com. "
                   "Check your connection and that you're logged into fab.com in Chrome or Firefox.")

    with open(asset_formats_file, "r") as f:
        data = json.load(f)

    asset_format = {'3d-model': 'fbx', 'material': 'texture-set', 'decal': 'texture-set'}.get(asset_type)
    if not asset_format:
        return 1, f"Unsupported asset type: {asset_type}"

    import_size = int(size)
    file_name = None
    file_uid = None
    for asset in data:
        if asset["assetFormatType"]["code"] == asset_format:
            while import_size >= 0:
                try:
                    file_name = asset["files"][import_size]["name"]
                    break
                except IndexError:
                    import_size -= 1
            file_uid = asset["files"][import_size]["uid"]
    print(f"UID for {asset_format}: {file_uid}")
    if not file_uid:
        return 1, f"{asset_format} not found"

    asset_path = os.path.join(paths["assets_dir"], file_name)
    extract_name = os.path.splitext(file_name)[0]
    extract_path = os.path.join(paths["unzipped_assets_dir"], extract_name)

    if not os.path.exists(extract_path):
        if not os.path.exists(asset_path):
            down_link_file = os.path.join(paths["json_dir"], f"downlink_{file_uid}.json")
            link_expired = True
            if os.path.exists(down_link_file):
                with open(down_link_file, "r") as f:
                    link_data = json.load(f)
                expires_dt = datetime.fromisoformat(link_data["downloadInfo"][0]["expires"].rstrip("Z")).replace(
                    tzinfo=timezone.utc)
                link_expired = datetime.now(timezone.utc) > expires_dt
            if link_expired:
                url = (f"https://www.fab.com/i/listings/{uid}/asset-formats/{asset_format}"
                       f"/files/{file_uid}/download-info")
                referer = f"https://www.fab.com/i/listings/{uid}"
                command = [paths["python_path"], FAB_API_SCRIPT, "--function", "fetch_down_link", url, referer,
                           paths["json_dir"], file_uid]
                print(f"Running {command} inside the virtual environment...")
                process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                print(process.communicate()[0])
            if not os.path.exists(down_link_file):
                return 1, ("Could not get a download link. Log into fab.com in Chrome or "
                           "Firefox, make sure the asset is in your library, then try again.")
            with open(down_link_file, "r") as f:
                link_data = json.load(f)
                down_link = link_data["downloadInfo"][0]["downloadUrl"]
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

    add_downloaded_asset(context, file_uid, display_name or extract_name, asset_type, asset_path, import_size, img_path)

    if import_type == "import_to_scene":
        if import_to_scene(context, file_name, asset_path, asset_type) != 0:
            return 1, "Asset Import Failed"
    elif import_type == "add_to_asset_library":
        prefs = context.preferences.addons[ADDON_ID].preferences
        blender_path = prefs.blender_executable_path
        if not blender_path or not os.path.isfile(blender_path):
            return 1, "Invalid Blender executable path!"
        command = [blender_path, "-b", "--factory-startup", "-P", ASSET_IMPORTER_SCRIPT, "--",
                   paths["assets_dir"], file_name, asset_path, asset_type, img_path or "No Image"]
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        com = process.communicate()[0]
        if process.returncode != 0:
            print("Error Importing and Marking Asset")
        else:
            print(str(com))
            refresh_asset_browser()

    return 0, "Asset Imported"


def update_assets(context, cursor):
    """Fetch a search page from Fab, then (in the background) download thumbnails and
    regenerate the placeholder library so results show up in the native Asset Browser.

    Returns ``None`` on success or an error string to surface to the user (the search
    otherwise fails silently and the Asset Browser just stays empty).
    """
    paths = get_asset_paths(context)
    if not is_valid_python_path(context.preferences.addons[ADDON_ID].preferences.system_python):
        return ("No usable Python environment. Set a valid 'System Python Path' in the "
                "addon preferences and click 'Setup Environment'.")
    asset_type = str(context.scene.asset_type).strip()
    query = context.scene.asset_search.strip()
    sort_method = context.scene.sort_method
    size = int(context.scene.import_size.strip())
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

    # The fetch runs synchronously above; if it produced no listings file the search
    # failed (usually a login/connection problem). Surface that instead of spawning a
    # background thread that would crash on the missing file and leave an empty library.
    if not os.path.exists(file_path):
        return ("Could not fetch search results from fab.com. Log into fab.com in Chrome "
                "or Firefox, then try again.")

    state.loading_thread = threading.Thread(
        target=load_assets_in_background, args=(file_path, asset_type, size, paths))
    state.loading_thread.start()
    return None


def load_assets_in_background(file_path, asset_type, size, paths):
    """Thread entry point: run the worker but never let an exception vanish into the
    thread (which would leave the library silently empty). Errors are printed with a
    clear marker so they show up in Blender's console / system terminal."""
    try:
        _load_assets_worker(file_path, asset_type, size, paths)
    except Exception as e:
        import traceback
        print(f"[quixel] Asset loading failed: {e}")
        traceback.print_exc()


def _load_assets_worker(file_path, asset_type, size, paths):
    """Runs off the main thread: download/crop thumbnails, accumulate a manifest of
    this page's results into :data:`state.manifest`, rebuild ``placeholders.blend`` via
    a headless Blender, then schedule an Asset Browser refresh on the main thread.
    """
    with open(file_path, 'r') as f:
        data = json.load(f)

    state.cursors["next_cursor"] = data.get("cursors", {}).get("next")

    entries = {}          # uid -> manifest entry (thumbnail_path filled in after download)
    items_to_download = []  # (uid, img_url, img_path)

    for item in data.get("results", []):
        if state.cancel_loading:
            print("Loading cancelled.")
            return
        category = item.get("category", {})
        if category.get("name") == "Plants":
            continue
        uid = item.get("uid", "")
        if not uid:
            continue
        entries[uid] = {
            "uid": uid,
            "asset_type": asset_type,
            "title": item.get("title", ""),
            "category_path": category.get("path", ""),
            "category_name": category.get("name", ""),
            "tags": [t.get("name") for t in item.get("tags", []) if t.get("name")],
            "thumbnail_path": "",
            "size": size,
        }

        images = (item.get("thumbnails") or [{}])[0].get("images", [])
        if images:
            img_url = min(images, key=lambda im: abs(im.get("height", 0) - 180)).get("url")
            if img_url:
                img_path = os.path.join(paths["thumbnail_dir"], os.path.basename(img_url))
                items_to_download.append((uid, img_url, img_path))

    def download_and_process(item):
        uid, img_url, img_path = item
        fresh = os.path.exists(img_path) and (
            datetime.now() - datetime.fromtimestamp(os.path.getmtime(img_path)) <= timedelta(days=5))
        if not fresh:
            try:
                subprocess.run([paths["python_path"], FAB_API_SCRIPT, "--function", "download_file", img_url, img_path],
                               check=True, capture_output=True, text=True)
                crop = "crop_thumbnails" if asset_type in ('material', 'decal') else "smart_square_crop"
                subprocess.run([paths["python_path"], FAB_API_SCRIPT, "--function", crop, img_path],
                               check=True, capture_output=True, text=True)
            except subprocess.CalledProcessError as e:
                print(f"Failed to download/process {uid}: {e}")
        return uid, (img_path if os.path.exists(img_path) else "")

    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
        for uid, thumb in executor.map(download_and_process, items_to_download):
            if state.cancel_loading:
                print("Loading cancelled.")
                return
            entries[uid]["thumbnail_path"] = thumb

    # Accumulate into the session manifest (dedupe by uid so "Load More" adds, not replaces).
    seen = {e["uid"] for e in state.manifest}
    state.manifest.extend(e for uid, e in entries.items() if uid not in seen)

    build_placeholders(paths)
    bpy.app.timers.register(_schedule_refresh)


def build_placeholders(paths):
    """Rebuild ``placeholders.blend`` from the accumulated manifest via headless Blender.

    Uses ``bpy.app.binary_path`` (the running Blender) so the saved .blend version can
    never be newer than the session that will read it.
    """
    with open(paths["placeholder_manifest"], "w") as f:
        json.dump(state.manifest, f)
    command = [bpy.app.binary_path, "-b", "--factory-startup", "-P", PLACEHOLDER_BUILDER_SCRIPT, "--",
               paths["placeholder_manifest"], paths["placeholders_blend"], paths["catalog_file"]]
    print(f"Building placeholders: {command}")
    result = subprocess.run(command, capture_output=True, text=True)
    print(result.stdout)
    if result.returncode != 0:
        print(f"Placeholder build failed: {result.stderr}")


def _schedule_refresh():
    """Main-thread timer callback: refresh open Asset Browsers after a build."""
    refresh_asset_browser()
    return None
