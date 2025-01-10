import argparse
import json
import os
import requests
import subprocess
import sys
import time
from PIL import Image

payload = ""

headers = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:133.0) Gecko/20100101 Firefox/133.0",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en",
    "Accept-Encoding": "gzip, deflate, br, zstd",
    "X-Requested-With": "XMLHttpRequest",
    "DNT": "1",
    "Alt-Used": "www.fab.com",
    "Connection": "keep-alive",
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
    "Sec-GPC": "1"
}

querystring = {
    "asset_formats": ["gltf"],
    "currency": "USD",
    "is_ai_generated": "0",
    "is_free": "1",
    "seller": "Quixel",
    "sort_by": "listingTypeWeight"
}

data_dir = "/tmp/fab_data"

if not os.path.exists(data_dir):
    os.mkdir(data_dir)


def crop_thumbnails(image_path):
    if image_path:
        image = Image.open(f"{image_path}")
        # Get the original dimensions
        width, height = image.size
        new_width = height
        top = 0
        bottom = height
        left = (width - new_width) // 2
        right = left + new_width
        # Crop the image
        cropped_image = image.crop((left, top, right, bottom))
        cropped_image.save(f"{image_path}")


def fetch_assets(url, referer, asset_type=None, query=None, cursor=None):
    headers["Referer"] = referer
    querystring["cursor"] = cursor
    querystring["listing_types"] = asset_type
    querystring["q"] = query

    file_path = os.path.join(data_dir, f"output_{asset_type}_{query}_{cursor}.json")

    fetcher(url, headers, file_path, query=querystring)


def fetch_asset_formats(url, referer, asset_uid=None):
    headers["Referer"] = referer
    file_path = os.path.join(data_dir, f"output_{asset_uid}.json")

    fetcher(url, headers, file_path)


def fetch_down_link(url, referer, asset_uid=None):
    headers["Referer"] = referer
    file_path = os.path.join(data_dir, f"output_{asset_uid}.json")

    fetcher(url, headers, file_path)


def fetcher(url, header, file_path, query=None):
    max_retries = 5  # Number of retries
    retry_delay = 2  # Delay in seconds between retries

    for attempt in range(1, max_retries + 1):
        try:
            # Make the GET request
            if query:
                response = requests.get(url, headers=header, params=query)
            else:
                response = requests.get(url, headers=header)

            if response.status_code == 200:
                # Success: Process the response
                try:
                    json_response = response.content.decode('utf-8')  # Decode without decompression
                    json_data = json.loads(json_response)  # Parse the decoded data as JSON

                    pretty_json = json.dumps(json_data, indent=2)

                    # Save the pretty-printed data to a file
                    with open(file_path, 'w') as f:
                        f.write(pretty_json)
                    print(f"Data saved to {file_path}")
                    return  # Exit the function on success

                except ValueError:
                    print("Decoded content is not in valid JSON format.")
                    return  # Exit the function if content is invalid

            elif response.status_code == 403:
                # Forbidden: Log and retry
                print(f"Attempt {attempt}: Received 403 Forbidden. Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
                continue

            else:
                # Other HTTP errors
                print(f"Attempt {attempt}: Received HTTP {response.status_code}. Exiting.")
                return

        except requests.RequestException as e:
            print(f"Attempt {attempt}: Request failed with exception: {e}. Retrying in {retry_delay} seconds...")
            time.sleep(retry_delay)
            continue

    print("All retry attempts failed. Exiting.")


def main(function_name, *args):
    if function_name == "crop_thumbnails":
        crop_thumbnails(*args)
    elif function_name == "fetch_assets":
        fetch_assets(*args)
    elif function_name == "fetch_asset_formats":
        fetch_asset_formats(*args)
    elif function_name == "fetch_down_link":
        fetch_down_link(*args)
    else:
        print("Function not found")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--function", required=True, help="Name of the function to run")
    parser.add_argument("args", nargs=argparse.REMAINDER, help="Arguments for the function")
    args = parser.parse_args()
    main(args.function, *args.args)

