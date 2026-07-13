"""Build the shared placeholder ("dummy") asset library from a search manifest.

Run head­less by the addon:

    blender -b --factory-startup -P placeholder_builder.py -- \
        <manifest.json> <placeholders.blend> <blender_assets.cats.txt>

For every entry in the manifest it creates a lightweight datablock (a Material for
surfaces/decals, an Empty Object for 3D models), marks it as an asset, assigns it to
a catalog derived from the Fab category, attaches tags and the downloaded thumbnail as
a custom preview, and stamps it with identity so the addon's drag-download handler can
recover which Fab asset to fetch. All dummies are saved into one ``placeholders.blend``.

Two identity channels are written, deliberately redundant:

* ``qib_asset`` PropertyGroup — this script registers a PropertyGroup with the *same*
  attribute name and layout the addon uses, so the values round-trip as ID properties
  into the user's session where the matching RNA type is registered.
* ``asset_data.description`` token ``QIB:{uid}:{asset_type}:{size}`` — a plain string
  that survives regardless of whether any custom property type is registered.

This is a subprocess script: it is executed by path and never imported, so the small
catalog/token helpers below are duplicated from ``src/catalog.py`` / ``src/dummy.py``.
Keep them in sync with those modules.
"""

import json
import os
import sys
import uuid

import bpy


# --- Duplicated helpers (keep in sync with src/catalog.py, src/dummy.py) ---

_TYPE_ROOT = {"3d-model": "3d", "material": "surface", "decal": "surface"}


def slug_to_display(slug):
    return " ".join(word.capitalize() for word in slug.split("-"))


def fab_category_to_catalog_path(listing_type, category_path, category_name=None):
    root = _TYPE_ROOT.get(listing_type, "surface")
    segments = [seg for seg in (category_path or "").split("/") if seg]
    parts = [root]
    for i, seg in enumerate(segments):
        is_leaf = i == len(segments) - 1
        parts.append(category_name if (is_leaf and category_name) else slug_to_display(seg))
    return "/".join(parts)


def catalog_simple_name(catalog_path):
    return catalog_path.replace("/", "-")


def read_catalogs(catalog_file):
    catalogs = {}
    if not os.path.exists(catalog_file):
        return catalogs
    with open(catalog_file, "r") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith(("#", "VERSION")):
                continue
            parts = line.split(":")
            if len(parts) >= 2:
                catalogs[parts[1]] = parts[0]
    return catalogs


def ensure_catalog(catalog_file, catalog_path, _cache):
    """Stable UUID for a catalog path; appends a new line if absent. ``_cache`` avoids
    re-reading the file for every asset in one build."""
    if not _cache:
        _cache.update(read_catalogs(catalog_file))
    if catalog_path in _cache:
        return _cache[catalog_path]
    catalog_uuid = str(uuid.uuid4())
    new_file = not os.path.exists(catalog_file)
    with open(catalog_file, "a") as f:
        if new_file:
            f.write("VERSION 1\n")
        f.write(f"{catalog_uuid}:{catalog_path}:{catalog_simple_name(catalog_path)}\n")
    _cache[catalog_path] = catalog_uuid
    return catalog_uuid


def make_token(uid, asset_type, size):
    return f"QIB:{uid}:{asset_type}:{size}"


# --- qib_asset PropertyGroup (matches src/dummy.py layout for round-trip) ---

class QIBAssetInfo(bpy.types.PropertyGroup):
    is_dummy: bpy.props.BoolProperty(default=False)
    fab_uid: bpy.props.StringProperty(default="")
    asset_type: bpy.props.StringProperty(default="")
    size: bpy.props.IntProperty(default=2)


def register_qib_asset():
    bpy.utils.register_class(QIBAssetInfo)
    for id_type in (bpy.types.Object, bpy.types.Material, bpy.types.World):
        id_type.qib_asset = bpy.props.PointerProperty(type=QIBAssetInfo)


def set_custom_preview(datablock, thumbnail_path):
    if not thumbnail_path or not os.path.exists(thumbnail_path):
        return
    override = bpy.context.copy()
    override["id"] = datablock
    with bpy.context.temp_override(**override):
        bpy.ops.ed.lib_id_load_custom_preview(filepath=thumbnail_path)


def make_dummy(entry, catalog_file, catalog_cache):
    asset_type = entry["asset_type"]
    title = entry.get("title") or entry["uid"]

    if asset_type == "3d-model":
        datablock = bpy.data.objects.new(title, None)  # Empty
    else:  # material / decal
        datablock = bpy.data.materials.new(title)

    datablock.use_fake_user = True
    datablock.asset_mark()

    catalog_path = fab_category_to_catalog_path(
        asset_type, entry.get("category_path", ""), entry.get("category_name"))
    datablock.asset_data.catalog_id = ensure_catalog(catalog_file, catalog_path, catalog_cache)

    for tag in entry.get("tags", []):
        datablock.asset_data.tags.new(tag, skip_if_exists=True)

    size = int(entry.get("size", 2))
    datablock.asset_data.description = make_token(entry["uid"], asset_type, size)
    set_custom_preview(datablock, entry.get("thumbnail_path"))

    info = datablock.qib_asset
    info.is_dummy = True
    info.fab_uid = entry["uid"]
    info.asset_type = asset_type
    info.size = size


def main(manifest_path, blend_path, catalog_file):
    with open(manifest_path, "r") as f:
        manifest = json.load(f)

    register_qib_asset()
    bpy.ops.wm.read_factory_settings(use_empty=True)

    catalog_cache = {}
    for entry in manifest:
        try:
            make_dummy(entry, catalog_file, catalog_cache)
        except Exception as e:
            print(f"Failed to build placeholder for {entry.get('uid')}: {e}")

    os.makedirs(os.path.dirname(blend_path), exist_ok=True)
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=blend_path)
    print(f"Saved {len(manifest)} placeholders to {blend_path}")


if __name__ == "__main__":
    argv = sys.argv[sys.argv.index("--") + 1:]
    main(argv[0], argv[1], argv[2])
