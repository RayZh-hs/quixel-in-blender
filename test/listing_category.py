import json

# Load JSON file
def load_json(filepath):
    with open(filepath, 'r') as f:
        return json.load(f)

# Recursively filter tree based on valid UIDs
def filter_tree_recursive(children, valid_uids):
    filtered_children = []
    for child in children:
        child['children'] = filter_tree_recursive(child.get('children', []), valid_uids)
        if child['uid'] in valid_uids or child['children']:
            filtered_children.append(child)
    return filtered_children

# Load data
tree_filepath = "/tmp/output_listing_tree.json"
count_filepath = "/tmp/output_listing_count.json"
filtered_tree_filepath = "/tmp/filtered_tree.json"

tree_data = load_json(tree_filepath)
count_data = load_json(count_filepath)

# Extract valid UIDs with docCount > 0 for '3d-model' and 'material'
valid_uids = set()
for category_key in ['3d-model', 'material']:
    if category_key in count_data['aggregations']['categoryPerListingType']['buckets']:
        for uid, details in count_data['aggregations']['categoryPerListingType']['buckets'][category_key]['category']['buckets'].items():
            if details['docCount'] > 0:
                valid_uids.add(uid)

# Create filtered tree with only '3d-model' and 'material'
filtered_tree = {
    '3d-model': filter_tree_recursive(tree_data.get('3d-model', []), valid_uids),
    'material': filter_tree_recursive(tree_data.get('material', []), valid_uids)
}

# Save filtered tree
with open(filtered_tree_filepath, 'w') as f:
    json.dump(filtered_tree, f, indent=2)

print(f"Filtered tree saved to {filtered_tree_filepath}")