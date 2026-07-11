"""Quixel in Blender — addon entry point.

This is the module Blender loads. It carries ``bl_info`` and delegates the actual
work to the :mod:`src` package: all logic (UI, operators, preferences, import,
paths/env, background loading) lives under ``src/``, while the two standalone
subprocess scripts live under ``scripts/``. See ``ARCHITECTURE.md`` for the
overall design.
"""

bl_info = {
    "name": "Quixel in Blender",
    "description": "Browse and import Megascans and Megaplants assets from the Fab marketplace",
    "author": "https://github.com/RayZh-hs/",
    "version": (5, 0, 0),
    "blender": (4, 4, 0),
    "location": "View3D > Sidebar > Quixel",
    "category": "Asset Management",
}

from . import src


def register():
    src.register()


def unregister():
    src.unregister()


if __name__ == "__main__":
    register()
