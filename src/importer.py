"""Importing downloaded assets into the current scene.

Handles extracting an asset ZIP, importing its FBX (for 3D models) or building a
material (for surfaces/decals), and wiring up a Principled-BSDF PBR shader from the
asset's texture maps. Also contains the download-progress reader used to drive
Blender's progress bar while a file downloads.

This is the "import into the active scene" path. The alternative "add to asset
library" path is handled out-of-process by ``scripts/asset_importer.py``.

Depends on :mod:`.constants` and :mod:`.paths`.
"""

import os
import zipfile

import bpy

from .paths import get_asset_paths


def import_to_scene(context, asset_name, asset_path, asset_type):
    paths = get_asset_paths(context)
    print(asset_name)
    print(asset_path)

    if asset_path.endswith(".zip"):
        extract_name = os.path.splitext(os.path.basename(asset_name))[0]
        extract_path = os.path.join(paths["unzipped_assets_dir"], extract_name)

        if os.path.exists(extract_path):
            print(f"Using extracted folder: {extract_path}")
        elif os.path.exists(asset_path):
            print(f"Extracting from ZIP: {asset_path}")
            try:
                with zipfile.ZipFile(asset_path, 'r') as zip_ref:
                    zip_ref.extractall(extract_path)
                print(f"Extracted {asset_name} to {extract_path}")
            except zipfile.BadZipFile:
                print(f"{asset_name} is not a valid ZIP file.")
                return 1
        else:
            print(f"Missing both ZIP and extracted folder for asset: {asset_name}")
            return 1

        if asset_type == '3d-model':
            for file_name in os.listdir(extract_path):
                if file_name.endswith(".fbx"):
                    fbx_path = os.path.join(extract_path, file_name)
                    bpy.ops.import_scene.fbx(filepath=fbx_path)
                    print(f"Imported FBX: {fbx_path}")
                    ass_name = os.path.splitext(os.path.basename(asset_name))[0]
                    new_collection = bpy.data.collections.new(ass_name)
                    bpy.context.scene.collection.children.link(new_collection)
                    new_empty = bpy.data.objects.new(ass_name, None)
                    new_collection.objects.link(new_empty)
                    bpy.ops.object.parent_clear(type='CLEAR_KEEP_TRANSFORM')
                    for obj in bpy.context.selected_objects:
                        for collection in obj.users_collection:
                            collection.objects.unlink(obj)
                        new_collection.objects.link(obj)
                        if obj.type == 'MESH':
                            obj.parent = new_empty
                            material_name = obj.name + "_mat"
                            material = bpy.data.materials.get(material_name)
                            if not material:
                                material = bpy.data.materials.new(name=material_name)
                                create_pbr_shader(material, extract_path)
                            obj.data.materials.clear()
                            obj.data.materials.append(material)
                        else:
                            bpy.data.objects.remove(obj)
                    bpy.context.view_layer.objects.active = new_empty
                    new_empty.select_set(True)
            return 0

        elif asset_type in ('material', 'decal'):
            ass_name = os.path.splitext(os.path.basename(asset_name))[0]
            active_object = bpy.context.active_object
            if active_object and active_object.type == 'MESH':
                print("Active Object Name:", active_object.name)
                material_name = ass_name + "_mat"
                material = bpy.data.materials.get(material_name)
                if not material:
                    material = bpy.data.materials.new(name=material_name)
                    create_pbr_shader(material, extract_path)
                active_object.data.materials.clear()
                active_object.data.materials.append(material)
                return 0
            else:
                print("Select a mesh object.")
                return 1
    return 1


def create_pbr_shader(material, texture_maps_path):
    # Enable 'Use Nodes' for the material
    material.use_nodes = True
    nodes = material.node_tree.nodes
    links = material.node_tree.links

    # Clear default nodes
    for node in nodes:
        nodes.remove(node)

    # Create a Principled BSDF shader
    principled_bsdf = nodes.new(type='ShaderNodeBsdfPrincipled')
    principled_bsdf.location = (100, 0)

    # Create Material Output node
    material_output = nodes.new(type='ShaderNodeOutputMaterial')
    material_output.location = (400, 0)

    # Link the Principled BSDF to the Material Output
    links.new(principled_bsdf.outputs['BSDF'], material_output.inputs['Surface'])

    # Create Texture Coordinate node
    tex_coord_node = nodes.new(type='ShaderNodeTexCoord')
    tex_coord_node.location = (-1200, 0)

    # Create Mapping node
    mapping_node = nodes.new(type='ShaderNodeMapping')
    mapping_node.location = (-1000, 0)

    # Link Texture Coordinate to Mapping
    links.new(tex_coord_node.outputs['UV'], mapping_node.inputs['Vector'])

    # Define texture map keywords
    texture_map_keywords = {
        'Base Color': 'BaseColor',
        'Metallic': 'Metalness',
        'Normal': 'Normal',
        'Roughness': 'Roughness',
        'Specular': 'Specular',
        'AO': 'AO',
        'Bump': 'Bump',
        'Opacity': 'Opacity',
        'Displacement': 'Displacement'
    }

    # Get all jpg files in the specified directory
    texture_files = [f for f in os.listdir(texture_maps_path) if f.endswith('.jpg')]

    normal_map = nodes.new(type='ShaderNodeNormalMap')
    normal_map.location = (-400, -200)

    # Load and set up texture maps
    texture_nodes = {}
    y_offset = 0  # Start Y-position for textures
    for map_type, keyword in texture_map_keywords.items():
        # Find the corresponding texture file
        texture_file = next((f for f in texture_files if keyword in f), None)
        if texture_file:
            texture_path = os.path.join(texture_maps_path, texture_file)
            if bpy.data.images.get(texture_file):
                image = bpy.data.images[texture_file]
            else:
                image = bpy.data.images.load(texture_path)

            # Create an Image Texture node
            image_texture = nodes.new(type='ShaderNodeTexImage')
            image_texture.label = map_type
            image_texture.image = image
            image_texture.location = (-750, y_offset)
            y_offset -= 300  # Move the next texture down

            # Set 'Non-Color' for specific maps
            if map_type in ['Roughness', 'Metallic', 'Normal', 'Specular', 'AO', 'Bump', 'Opacity', 'Displacement']:
                image.colorspace_settings.name = 'Non-Color'

            texture_nodes[map_type] = image_texture

            # Connect Mapping node to each texture's vector input
            links.new(mapping_node.outputs['Vector'], image_texture.inputs['Vector'])

    # Connect Base Color and AO
    if 'Base Color' in texture_nodes:
        if 'AO' in texture_nodes:
            mix_rgb = nodes.new(type='ShaderNodeMixRGB')
            mix_rgb.blend_type = 'MULTIPLY'
            mix_rgb.location = (-200, 0)
            links.new(texture_nodes['Base Color'].outputs['Color'], mix_rgb.inputs[1])
            links.new(texture_nodes['AO'].outputs['Color'], mix_rgb.inputs[2])
            links.new(mix_rgb.outputs['Color'], principled_bsdf.inputs['Base Color'])
        else:
            links.new(texture_nodes['Base Color'].outputs['Color'], principled_bsdf.inputs['Base Color'])

    # Connect Roughness
    if 'Roughness' in texture_nodes:
        links.new(texture_nodes['Roughness'].outputs['Color'], principled_bsdf.inputs['Roughness'])

    # Connect Metallic
    if 'Metallic' in texture_nodes:
        links.new(texture_nodes['Metallic'].outputs['Color'], principled_bsdf.inputs['Metallic'])

    # Connect Specular
    if 'Specular' in texture_nodes:
        links.new(texture_nodes['Specular'].outputs['Color'], principled_bsdf.inputs['Specular IOR Level'])

    # Connect Opacity
    if 'Opacity' in texture_nodes:
        links.new(texture_nodes['Opacity'].outputs['Color'], principled_bsdf.inputs['Alpha'])

    # Connect Displacement
    if 'Displacement' in texture_nodes:
        displacement_node = nodes.new(type='ShaderNodeDisplacement')
        displacement_node.location = (100, -400)
        links.new(texture_nodes['Displacement'].outputs['Color'], displacement_node.inputs['Height'])
        links.new(displacement_node.outputs['Displacement'], material_output.inputs['Displacement'])

    # Connect Normal and Bump
    if 'Normal' in texture_nodes:
        if 'Bump' in texture_nodes:
            bump_node = nodes.new(type='ShaderNodeBump')
            bump_node.inputs['Strength'].default_value = 0.1
            bump_node.inputs['Distance'].default_value = 0.1
            bump_node.location = (-200, -200)
            links.new(texture_nodes['Bump'].outputs['Color'], bump_node.inputs['Height'])
            links.new(texture_nodes['Normal'].outputs['Color'], normal_map.inputs['Color'])
            links.new(normal_map.outputs['Normal'], bump_node.inputs['Normal'])
            links.new(bump_node.outputs['Normal'], principled_bsdf.inputs['Normal'])
        else:
            links.new(texture_nodes['Normal'].outputs['Color'], normal_map.inputs['Color'])
            links.new(normal_map.outputs['Normal'], principled_bsdf.inputs['Normal'])


def update_ui_with_progress(process):
    wm = bpy.context.window_manager
    wm.progress_begin(0, 100)

    try:
        for line in iter(process.stdout.readline, ''):
            if "Download Progress" in line:
                progress = float(line.split("Download Progress:")[1].strip().replace('%', ''))
                print(f"\rDownloading... {progress:.2f}%", end='')
                wm.progress_update(progress)
    except Exception as e:
        print(f"Error updating progress: {e}")
    finally:
        wm.progress_end()
