import bpy
import os

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
    principled_bsdf.location = (200, 0)

    # Create Material Output node
    material_output = nodes.new(type='ShaderNodeOutputMaterial')
    material_output.location = (600, 0)

    # Link the Principled BSDF to the Material Output
    links.new(principled_bsdf.outputs['BSDF'], material_output.inputs['Surface'])

    # Define texture map keywords
    texture_map_keywords = {
        'Base Color': 'BaseColor',
        'Metallic': 'Metalness',
        'Normal': 'Normal',
        'Roughness': 'Roughness',
        'Specular': 'Specular',
        'AO': 'AO',
        'Bump': 'Bump'
    }

    # Get all jpg files in the specified directory
    texture_files = [f for f in os.listdir(texture_maps_path) if f.endswith('.jpg')]

    # Create nodes for AO and Bump mapping
    mix_rgb = nodes.new(type='ShaderNodeMixRGB')
    mix_rgb.blend_type = 'MULTIPLY'
    mix_rgb.location = (-200, 0)

    bump_node = nodes.new(type='ShaderNodeBump')
    bump_node.inputs['Strength'].default_value = 0.1
    bump_node.inputs['Distance'].default_value = 0.1
    bump_node.location = (-200, -200)

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
            if map_type in ['Roughness', 'Metallic', 'Normal', 'Specular', 'AO', 'Bump']:
                image.colorspace_settings.name = 'Non-Color'

            texture_nodes[map_type] = image_texture

    # Connect Base Color
    if 'Base Color' in texture_nodes:
        links.new(texture_nodes['Base Color'].outputs['Color'], mix_rgb.inputs[1])

    # Connect AO to MixRGB
    if 'AO' in texture_nodes:
        links.new(texture_nodes['AO'].outputs['Color'], mix_rgb.inputs[2])

    # Connect MixRGB output to Principled BSDF Base Color
    links.new(mix_rgb.outputs['Color'], principled_bsdf.inputs['Base Color'])

    # Connect Roughness
    if 'Roughness' in texture_nodes:
        links.new(texture_nodes['Roughness'].outputs['Color'], principled_bsdf.inputs['Roughness'])

    # Connect Metallic
    if 'Metallic' in texture_nodes:
        links.new(texture_nodes['Metallic'].outputs['Color'], principled_bsdf.inputs['Metallic'])

    # Connect Specular
    if 'Specular' in texture_nodes:
        links.new(texture_nodes['Specular'].outputs['Color'], principled_bsdf.inputs['Specular IOR Level'])

    # Connect Normal and Bump
    if 'Normal' in texture_nodes:
        links.new(texture_nodes['Normal'].outputs['Color'], normal_map.inputs['Color'])

    if 'Bump' in texture_nodes:
        links.new(texture_nodes['Bump'].outputs['Color'], bump_node.inputs['Height'])

    # Connect Bump to Normal and then to Principled BSDF
    links.new(normal_map.outputs['Normal'], bump_node.inputs['Normal'])
    links.new(bump_node.outputs['Normal'], principled_bsdf.inputs['Normal'])

# Apply material to selected objects
objs = bpy.context.selected_objects
texture_maps_path = "/tmp/quixel/rusty_gas_tank/fbx/"

for ob in objs:
    material_name = ob.name + "_mat"
    material = bpy.data.materials.get(material_name)
    if not material:
        material = bpy.data.materials.new(name=material_name)
        create_pbr_shader(material, texture_maps_path)
    ob.data.materials.clear()
    ob.data.materials.append(material)
