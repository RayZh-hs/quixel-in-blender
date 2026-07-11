"""Thumbnail preview-collection lifecycle.

Wraps Blender's ``bpy.utils.previews`` collection that backs every thumbnail icon
in the panel. Created at register time (seeded with the placeholder image and any
already-downloaded thumbnails) and removed at unregister time. The live collection
handle is kept on :data:`state.preview_collection`.

Depends on :mod:`.constants`, :mod:`.state` and :mod:`.assets`.
"""

import os

import bpy.utils.previews

from . import state
from .constants import PREVIEW_IMG
from .assets import load_downloaded_assets
from .paths import get_asset_paths


def initialize_preview_collection(context):
    paths = get_asset_paths(context)
    if not state.preview_collection:
        state.preview_collection = bpy.utils.previews.new()
        state.preview_collection.load("preview", PREVIEW_IMG, 'IMAGE')

    # Load thumbnails for downloaded assets
    downloaded_assets = load_downloaded_assets(context)
    for uid, asset_data in downloaded_assets.items():
        thumbnail_path = asset_data["thumbnail_image"]
        if os.path.exists(thumbnail_path):
            state.preview_collection.load(uid, thumbnail_path, 'IMAGE')


def cleanup_preview_collection():
    if state.preview_collection:
        bpy.utils.previews.remove(state.preview_collection)
        state.preview_collection = None
