import bpy
import json
import os
import sys
import uuid
import zipfile
import logging


def initialize_paths(base_path):
    """Initializes and returns essential paths."""
    unzipped_assets_dir = os.path.join(base_path, "unzipped_assets")
    blender_files_dir = os.path.join(base_path, "blender_files")
    catalog_file = os.path.join(base_path, "blender_assets.cats.txt")

    # Create directories if they don't exist
    os.makedirs(unzipped_assets_dir, exist_ok=True)
    os.makedirs(blender_files_dir, exist_ok=True)

    return unzipped_assets_dir, blender_files_dir, catalog_file


def initialize_catalog_file(catalog_file):
    """Initializes the catalog file if it doesn't exist."""
    if not os.path.exists(catalog_file):
        with open(catalog_file, 'w') as f:
            f.write(f"VERSION 1\n{str(uuid.uuid4())}:3d:3d\n{str(uuid.uuid4())}:surface:surface\n")
            print(f"Initialized catalog file at {catalog_file}")


def get_asset_type(json_path):
    """Reads the JSON file and extracts the asset type."""
    try:
        with open(json_path, 'r') as file:
            data = json.load(file)
        asset_categories = data.get("assetCategories", {})
        if asset_categories:
            return next(iter(asset_categories), "Unknown")
        return "Unknown"
    except (json.JSONDecodeError, FileNotFoundError) as e:
        print(f"Error reading JSON file {json_path}: {e}")
        return "Invalid"


def find_json_file(folder_path, search_term):
    """Searches for a JSON file in the folder containing the given search term."""
    for file_name in os.listdir(folder_path):
        if file_name.endswith(".json") and file_name.strip(".json").lower() in search_term.lower():
            return os.path.join(folder_path, file_name)
    return None


def get_asset_categories(json_path):
    """Reads the JSON file and extracts the asset categories."""
    try:
        with open(json_path, 'r') as file:
            data = json.load(file)
        categories = data.get("categories")
        if categories:
            return str('-'.join(categories))
        return "unknown"
    except (json.JSONDecodeError, FileNotFoundError) as e:
        print(f"Error reading JSON file {json_path}: {e}")
        return "invalid"


def get_asset_tags(json_path):
    """Reads the JSON file and extracts the asset tags."""
    try:
        with open(json_path, 'r') as file:
            data = json.load(file)
        tags = data.get("tags")
        if tags:
            return tags
        return None
    except (json.JSONDecodeError, FileNotFoundError) as e:
        print(f"Error reading JSON file {json_path}: {e}")
        return None


def import_and_mark_asset(base_path, asset_name, asset_path, asset_type, preview_img):
    print(asset_name)
    print(asset_path)

    unzipped_assets_dir, blender_files_dir, catalog_file = initialize_paths(base_path)
    initialize_catalog_file(catalog_file)


    if asset_path.endswith(".zip"):
        extract_path = os.path.join(unzipped_assets_dir, asset_name[:-4])
        ass_name = os.path.splitext(os.path.basename(asset_name))[0]
        blend_file_path = os.path.join(blender_files_dir, f"{ass_name}.blend")

        # Check if the asset is already unzipped
        if not os.path.exists(extract_path):
            try:
                with zipfile.ZipFile(asset_path, 'r') as zip_ref:
                    zip_ref.extractall(extract_path)
                print(f"Extracted {asset_name} to {extract_path}")
            except zipfile.BadZipFile:
                print(f"{asset_name} is not a valid ZIP file.")
                return
        else:
            print(f"Asset '{asset_name}' is already unzipped. Skipping extraction.")

        json_file = find_json_file(extract_path, asset_name)
        if not json_file:
            print(f"No JSON file found for {asset_name}. Skipping.")
            return

        # asset_type = get_asset_type(json_file)
        category = get_asset_categories(json_file)
        tags = get_asset_tags(json_file)
        for fbx_file_name in os.listdir(extract_path):
            if fbx_file_name.endswith(".fbx"):
                fbx_path = os.path.join(extract_path, fbx_file_name)
                if not os.path.exists(preview_img):
                    preview_img = None

        try:
            # Read the catalog file to gather existing categories
            existing_categories = {}
            if os.path.exists(catalog_file):
                with open(catalog_file, 'r') as cf:
                    for line in cf:
                        if ':' in line:
                            existing_uuid = line.split(':')[0].strip()
                            existing_category = line.split(':')[-1].strip()
                            existing_categories[existing_category] = existing_uuid

            # If categories is not in the catalog file, append it
            if category not in existing_categories.keys():
                catalog_uuid = str(uuid.uuid4())
                category_path = category.replace("-", "/")
                with open(catalog_file, 'a') as cf:
                    cf.write(f"{catalog_uuid}:{category_path}:{category}\n")
                    print(f"Added new catalog ID: {category} to {catalog_file}")
                assigned_catalog_uuid = catalog_uuid
            else:
                assigned_catalog_uuid = existing_categories[category]

            if asset_type == '3d-model':
                # Clear the existing scene
                bpy.ops.wm.read_factory_settings(use_empty=True)

                # Import the fbx file
                bpy.ops.import_scene.fbx(filepath=fbx_path)
                print(f"Imported FBX: {fbx_path}")

                # Create a collection for the asset
                new_collection = bpy.data.collections.new(ass_name)
                bpy.context.scene.collection.children.link(new_collection)

                # Move imported objects to the new collection
                for obj in bpy.context.selected_objects:
                    bpy.context.scene.collection.objects.unlink(obj)
                    new_collection.objects.link(obj)
                    bpy.context.view_layer.objects.active = obj
                    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

                    if obj.type == 'MESH':
                        bpy.ops.object.parent_clear(type='CLEAR_KEEP_TRANSFORM')
                        obj.name = ass_name + '_' + '_'.join(obj.name.split('_')[1:])

                        material_name = obj.name + "_mat"
                        material = bpy.data.materials.get(material_name)
                        if not material:
                            material = bpy.data.materials.new(name=material_name)
                            create_pbr_shader(material, extract_path)
                        obj.data.materials.clear()
                        obj.data.materials.append(material)

                        # Mark the object as an asset
                        obj.asset_mark()
                        obj.asset_data.catalog_id = assigned_catalog_uuid
                        print(f"Marked object '{obj.name}' as asset with catalog ID {assigned_catalog_uuid}")

                        if tags:
                            for tag_name in tags:
                                obj.asset_data.tags.new(tag_name, skip_if_exists=True)

                        # Set custom preview image for the object
                        if preview_img and os.path.exists(preview_img):
                            override = bpy.context.copy()
                            override["id"] = obj
                            with bpy.context.temp_override(**override):
                                bpy.ops.ed.lib_id_load_custom_preview(filepath=preview_img)
                            print(f"Set custom preview image for object '{obj.name}'")
                    else:
                        bpy.data.objects.remove(obj)

            if asset_type == 'material' or asset_type == 'decal':
                bpy.ops.wm.read_factory_settings(use_empty=True)

                material_name = ass_name + "_mat"
                material = bpy.data.materials.get(material_name)

                if not material:
                    material = bpy.data.materials.new(name=material_name)
                    create_pbr_shader(material, extract_path)

                material.asset_mark()
                material.asset_data.catalog_id = assigned_catalog_uuid
                print(f"Marked material '{material.name}' as asset with catalog ID {assigned_catalog_uuid}")

                if tags:
                    for tag_name in tags:
                        material.asset_data.tags.new(tag_name, skip_if_exists=True)

                # Set custom preview image for material
                if preview_img and os.path.exists(preview_img):
                    override = bpy.context.copy()
                    override["id"] = material
                    with bpy.context.temp_override(**override):
                        bpy.ops.ed.lib_id_load_custom_preview(filepath=preview_img)
                    print(f"Set custom preview image for material '{material.name}'")

            # Disable .blend1 backup creation
            bpy.context.preferences.filepaths.save_version = 0

            # Save the Blender file
            bpy.ops.wm.save_as_mainfile(filepath=blend_file_path)
            print(f"Saved {blend_file_path}")
            return

        except Exception as e:
            print(f"Failed to process {fbx_path}: {e}")


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



print(str(sys.argv[-1]))
print(str(sys.argv[-2]))

import_and_mark_asset(str(sys.argv[-5]), str(sys.argv[-4]), str(sys.argv[-3]), str(sys.argv[-2]), str(sys.argv[-1]))
