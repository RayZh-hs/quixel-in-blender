"""Drag-download: turn a dropped placeholder into a real Fab asset.

Online search results live in the Asset Browser as lightweight "dummy" datablocks
(see :mod:`.dummy`). When the user drags one into the scene it is appended as a real
datablock carrying ``qib_asset.is_dummy == True``. A persistent ``depsgraph_update_pre``
handler notices that, *claims* the dummy (clears its flag so it is handled once),
removes it, and enqueues a job; a main-thread timer then runs the existing Fab
download+build pipeline (:func:`assets.download_and_build_asset`).

The blocking download deliberately runs in the timer, never inside the depsgraph
handler — the handler must stay fast and free of re-entrancy. ``undo_post`` /
``redo_post`` strip any lingering dummy so undo/redo of a drag can't resurrect one.

Depends on :mod:`.state`, :mod:`.dummy` and :mod:`.assets`.
"""

import bpy
from bpy.app import handlers

from . import state
from .assets import download_and_build_asset
from .dummy import parse_token

# Guard so the download's own scene edits don't re-trigger the handler.
_processing = False


def _identity(datablock):
    """Return ``(uid, asset_type, size)`` for a dummy, or ``None`` if it isn't one.

    Prefers the typed ``qib_asset`` group; falls back to the ``asset_data.description``
    token (which survives even if the custom property didn't round-trip).
    """
    info = getattr(datablock, "qib_asset", None)
    if info and info.is_dummy and info.fab_uid:
        return info.fab_uid, info.asset_type, info.size
    asset_data = getattr(datablock, "asset_data", None)
    if asset_data:
        parsed = parse_token(asset_data.description)
        if parsed:
            return parsed["uid"], parsed["asset_type"], parsed["size"]
    return None


def _is_dummy(datablock):
    info = getattr(datablock, "qib_asset", None)
    if info and info.is_dummy:
        return True
    asset_data = getattr(datablock, "asset_data", None)
    return bool(asset_data and parse_token(asset_data.description))


def _claim(datablock):
    """Mark a dummy as handled so it is never processed twice.

    Both detection channels must be neutralised: the ``qib_asset`` flag *and* the
    ``asset_data.description`` token (otherwise the token would keep the datablock
    looking like a dummy until the timer removes it, causing a duplicate download).
    Capture identity with :func:`_identity` before calling this.
    """
    info = getattr(datablock, "qib_asset", None)
    if info:
        info.is_dummy = False
    asset_data = getattr(datablock, "asset_data", None)
    if asset_data and parse_token(asset_data.description):
        asset_data.description = ""


@handlers.persistent
def on_depsgraph_pre(scene, depsgraph=None):
    """Detect dropped placeholders and enqueue their real downloads."""
    global _processing
    if bpy.app.background or _processing:
        return

    # World placeholder (future HDRIs).
    world = scene.world
    if world and _is_dummy(world):
        ident = _identity(world)
        _claim(world)
        if ident:
            state.pending_downloads.append({
                "kind": "world", "dummy_name": world.name,
                "uid": ident[0], "asset_type": ident[1], "size": ident[2],
                "target_object": None})

    # Material placeholder dropped onto an object → find the slot holding it.
    for obj in scene.objects:
        for slot in obj.material_slots:
            mat = slot.material
            if mat and _is_dummy(mat):
                ident = _identity(mat)
                _claim(mat)
                if ident:
                    state.pending_downloads.append({
                        "kind": "material", "dummy_name": mat.name,
                        "uid": ident[0], "asset_type": ident[1], "size": ident[2],
                        "target_object": obj.name})

    # 3D-model placeholder (Empty) dropped into the scene.
    for obj in scene.objects:
        if _is_dummy(obj):
            ident = _identity(obj)
            _claim(obj)
            if ident:
                state.pending_downloads.append({
                    "kind": "object", "dummy_name": obj.name,
                    "uid": ident[0], "asset_type": ident[1], "size": ident[2],
                    "target_object": None})

    if state.pending_downloads and not bpy.app.timers.is_registered(drain_pending):
        bpy.app.timers.register(drain_pending)


def _remove_dummy(kind, name):
    collection = {"material": bpy.data.materials,
                  "object": bpy.data.objects,
                  "world": bpy.data.worlds}[kind]
    datablock = collection.get(name)
    if datablock is not None:
        collection.remove(datablock)


def drain_pending():
    """Main-thread timer: process one queued drag-download per tick."""
    global _processing
    if not state.pending_downloads:
        return None

    job = state.pending_downloads.pop(0)
    context = bpy.context
    _processing = True
    try:
        _remove_dummy(job["kind"], job["dummy_name"])

        # A material must land on its drop target, which import_to_scene assigns to
        # the active object.
        if job["kind"] == "material" and job["target_object"]:
            target = bpy.data.objects.get(job["target_object"])
            if target:
                context.view_layer.objects.active = target
                target.select_set(True)

        status, message = download_and_build_asset(
            context, job["uid"], job["asset_type"], job["size"], "import_to_scene")
        if status != 0:
            print(f"Drag-download failed: {message}")
    except Exception as e:
        print(f"Drag-download error: {e}")
    finally:
        _processing = False

    return 0.1 if state.pending_downloads else None


@handlers.persistent
def on_undo_redo(scene, _=None):
    """Strip any lingering dummy so undo/redo of a drag can't resurrect one."""
    if scene.world and _is_dummy(scene.world):
        bpy.data.worlds.remove(scene.world)
    for obj in list(scene.objects):
        if _is_dummy(obj):
            bpy.data.objects.remove(obj)
            continue
        for slot in obj.material_slots:
            if slot.material and _is_dummy(slot.material):
                bpy.data.materials.remove(slot.material)


def register_handlers():
    handlers.depsgraph_update_pre.append(on_depsgraph_pre)
    handlers.undo_post.append(on_undo_redo)
    handlers.redo_post.append(on_undo_redo)


def unregister_handlers():
    for handler_list in (handlers.depsgraph_update_pre,):
        for fn in list(handler_list):
            if fn is on_depsgraph_pre:
                handler_list.remove(fn)
    for handler_list in (handlers.undo_post, handlers.redo_post):
        for fn in list(handler_list):
            if fn is on_undo_redo:
                handler_list.remove(fn)
    if bpy.app.timers.is_registered(drain_pending):
        bpy.app.timers.unregister(drain_pending)
    state.pending_downloads.clear()
