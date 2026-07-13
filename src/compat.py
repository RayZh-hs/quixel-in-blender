"""Blender-version gating.

The addon keeps a working floor at Blender 4.4 while opting into niceties that only
exist on newer Blenders (5.2+): an Asset Shelf quick-access surface and the native
"Packing" import method for self-contained downloaded ``.blend`` files.

Rather than sprinkling ``if bpy.app.version >= ...`` everywhere, classes tag
themselves with :func:`requires_blender_version` and are registered through
:func:`register_gated`, which silently skips any class whose floor the running
Blender does not meet. Optional code paths guard with :func:`run_if`.

Nothing here imports other addon modules, so it is safe to import from anywhere.
"""

import bpy


def requires_blender_version(min):
    """Class decorator tagging a minimum Blender version, e.g. ``(5, 2, 0)``.

    :func:`register_gated` reads the tag and skips the class on older Blenders.
    """
    def decorator(cls):
        cls._qib_min_version = tuple(min)
        return cls
    return decorator


def meets(min):
    """True if the running Blender is at least ``min`` (a version tuple)."""
    return bpy.app.version >= tuple(min)


def run_if(min):
    """Guard for optional code paths; alias of :func:`meets` reading at call time."""
    return meets(min)


def register_gated(classes):
    """Register only the classes whose ``_qib_min_version`` floor is met.

    Returns the list of classes actually registered so the caller can unregister
    exactly those. Registration failures (e.g. an experimental API differing on a
    newer Blender) are caught and logged rather than aborting the whole addon.
    """
    registered = []
    for cls in classes:
        min_version = getattr(cls, "_qib_min_version", None)
        if min_version is not None and not meets(min_version):
            continue
        try:
            bpy.utils.register_class(cls)
            registered.append(cls)
        except Exception as e:
            print(f"Skipping gated class {getattr(cls, '__name__', cls)}: {e}")
    return registered
