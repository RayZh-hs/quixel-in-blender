"""Placeholder-asset identity: the ``qib_asset`` PropertyGroup.

Online search results appear in the Asset Browser as lightweight "dummy" datablocks
(a Material for surfaces/decals, an Empty Object for 3D models). Each dummy carries a
:class:`QIBAssetInfo` telling the drag-download handler which Fab asset to fetch when
the dummy is dragged into the scene.

The same identity is *also* baked into the asset's ``asset_data.description`` as a
token (``QIB:{uid}:{asset_type}:{size}``) so it survives even if a Blender version
drops custom properties across an append. :func:`parse_token` reads that fallback.

Registration order matters: :class:`QIBAssetInfo` must be registered before the
``PointerProperty`` links are assigned onto Object/Material/World — see
:func:`register_dummy_properties`, called from the package ``register()``.
"""

import bpy

# ID types that can be dropped from the Asset Browser and thus need the pointer.
# World is included for future HDRI support even though Quixel's current types are
# only materials, decals and 3D models.
_ID_TYPES = (bpy.types.Object, bpy.types.Material, bpy.types.World)

_TOKEN_PREFIX = "QIB"


def make_token(uid, asset_type, size):
    """Serialise identity for the ``asset_data.description`` fallback."""
    return f"{_TOKEN_PREFIX}:{uid}:{asset_type}:{size}"


def parse_token(description):
    """Parse a ``QIB:uid:asset_type:size`` token, or ``None`` if not one."""
    if not description or not description.startswith(_TOKEN_PREFIX + ":"):
        return None
    parts = description.split(":")
    if len(parts) != 4:
        return None
    _, uid, asset_type, size = parts
    try:
        size = int(size)
    except ValueError:
        size = 2
    return {"uid": uid, "asset_type": asset_type, "size": size}


class QIBAssetInfo(bpy.types.PropertyGroup):
    is_dummy: bpy.props.BoolProperty(default=False)
    fab_uid: bpy.props.StringProperty(default="")
    asset_type: bpy.props.StringProperty(default="")
    size: bpy.props.IntProperty(default=2)


def register_dummy_properties():
    """Attach ``qib_asset`` to every draggable ID type (after class registration)."""
    for id_type in _ID_TYPES:
        id_type.qib_asset = bpy.props.PointerProperty(type=QIBAssetInfo)


def unregister_dummy_properties():
    for id_type in _ID_TYPES:
        if hasattr(id_type, "qib_asset"):
            del id_type.qib_asset
