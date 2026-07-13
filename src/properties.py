"""Scene-level properties and their (un)registration.

These ``bpy.types.Scene`` properties hold the panel's UI state: current mode,
asset type, import size/type, the search string and sort method, plus the separate
filters for the Downloaded tab. The search string and sort method re-run the search
operator on change via their ``update`` callback.

Registered/unregistered from :func:`.register`; kept separate from class
registration for clarity. Imports :mod:`.operators` for the search callback.
"""

import bpy

from .operators import FILEBROWSER_OT_search_assets


def register_properties():
    bpy.types.Scene.asset_search = bpy.props.StringProperty(
        name="Search Assets",
        update=FILEBROWSER_OT_search_assets.execute
    )
    bpy.types.Scene.asset_type = bpy.props.StringProperty(
        name="Asset Type",
        default='3d-model'
    )
    bpy.types.Scene.import_type = bpy.props.StringProperty(
        name="Import Type",
        default='import_to_scene'
    )
    bpy.types.Scene.import_size = bpy.props.StringProperty(
        name="Import Size",
        default='2'
    )
    bpy.types.Scene.sort_method = bpy.props.EnumProperty(
        name="Sort Method",
        description="Sort assets by different criteria",
        items=[
            ('newest', "Newest", "Sort by newest first"),
            ('oldest', "Oldest", "Sort by oldest first"),
            ('title_asc', "Title A-Z", "Sort by title alphabetically (A-Z)"),
            ('title_desc', "Title Z-A", "Sort by title alphabetically (Z-A)"),
        ],
        default='newest',
        update=FILEBROWSER_OT_search_assets.execute
    )


def unregister_properties():
    del bpy.types.Scene.asset_search
    del bpy.types.Scene.asset_type
    del bpy.types.Scene.import_type
    del bpy.types.Scene.import_size
    del bpy.types.Scene.sort_method
