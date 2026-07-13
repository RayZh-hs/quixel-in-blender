"""Mapping Fab categories onto Blender asset catalogs.

Blender's Asset Browser draws a left-hand navigation tree from the catalogs defined
in ``blender_assets.cats.txt`` (one line per catalog: ``UUID:path/with/slashes:simple_name``).
Fab search results carry a category like ``{"name": "Water", "path": "nature-terrain/water"}``;
turning that into a catalog path such as ``surface/Nature Terrain/Water`` makes the
native browser mirror Quixel Bridge's Environment▸Natural▸… hierarchy.

Two invariants matter:

* **UUID stability.** A catalog UUID is assigned once per path and never regenerated,
  so a placeholder asset and the real asset downloaded later land in the same node.
  :func:`ensure_catalog` always reuses an existing path's UUID.
* **Shared file.** The placeholder builder and the "Add To Assets" importer both write
  the *same* ``blender_assets.cats.txt`` (in ``assets_dir``); both dedupe by full path.

The ~pure helpers here are also duplicated into ``scripts/placeholder_builder.py``
because ``scripts/`` is executed as subprocesses and never imported (see architecture
docs). Keep the two copies in sync.
"""

import os
import uuid

# Fab listing type -> top-level catalog folder (matches the seed catalog written by
# paths.initialize_paths / asset_importer.py: "3d" and "surface").
_TYPE_ROOT = {
    "3d-model": "3d",
    "material": "surface",
    "decal": "surface",
}


def slug_to_display(slug):
    """``"nature-terrain"`` -> ``"Nature Terrain"`` (hyphen slug to Title Case)."""
    return " ".join(word.capitalize() for word in slug.split("-"))


def fab_category_to_catalog_path(listing_type, category_path, category_name=None):
    """Build a Blender catalog path from a Fab category.

    ``listing_type`` picks the top folder ("3d"/"surface"); ``category_path`` is the
    Fab slug path (``"nature-terrain/water"``). Intermediate segments are title-cased;
    the leaf uses ``category_name`` when given (the human label, e.g. "Water").
    """
    root = _TYPE_ROOT.get(listing_type, "surface")
    segments = [seg for seg in (category_path or "").split("/") if seg]
    parts = [root]
    for i, seg in enumerate(segments):
        is_leaf = i == len(segments) - 1
        parts.append(category_name if (is_leaf and category_name) else slug_to_display(seg))
    return "/".join(parts)


def catalog_simple_name(catalog_path):
    """Blender's third catalog field: the path with ``/`` replaced by ``-``."""
    return catalog_path.replace("/", "-")


def read_catalogs(catalog_file):
    """Return ``{catalog_path: uuid}`` parsed from an existing catalog file."""
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


def ensure_catalog(catalog_file, catalog_path):
    """Return the stable UUID for ``catalog_path``, appending a new line if absent.

    Reuses an existing path's UUID (never regenerates). Creates the file with a
    ``VERSION 1`` header if it does not yet exist.
    """
    catalogs = read_catalogs(catalog_file)
    if catalog_path in catalogs:
        return catalogs[catalog_path]

    catalog_uuid = str(uuid.uuid4())
    new_file = not os.path.exists(catalog_file)
    with open(catalog_file, "a") as f:
        if new_file:
            f.write("VERSION 1\n")
        f.write(f"{catalog_uuid}:{catalog_path}:{catalog_simple_name(catalog_path)}\n")
    return catalog_uuid
