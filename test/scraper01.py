import sys
import os
import subprocess
import argparse
import time
import platform
import cloudscraper
import json
import tempfile

parser = argparse.ArgumentParser(description="Utility to get assets")
parser.add_argument("--asset_type", type=str, required=True, help="asset type")
parser.add_argument("--query", type=str, required=True, help="search query")
args = parser.parse_args()

tempdir = tempfile.gettempdir()

url = "https://www.fab.com/i/listings/search"
referer = "https://www.fab.com/sellers/Quixel"

if platform.system() == 'Windows':
    user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:134.0) Gecko/20100101 Firefox/134.0"
else:
    user_agent = "Mozilla/5.0 (X11; Linux x86_64; rv:134.0) Gecko/20100101 Firefox/134.0"

headers = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Encoding": "gzip, deflate, br, zstd",
    "Accept-Language": "en",
    "Alt-Used": "www.fab.com",
    "Connection": "keep-alive",
    "Dnt": "1",
    "Referer": referer,
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
    "Sec-GPC": "1",
    "User-Agent": user_agent,
    "X-Requested-With": "XMLHttpRequest",
    # Adding Client Hints
    "Sec-CH-UA": '"Chromium";v="132", "Not A(Brand";v="99", "Google Chrome";v="132"',
    "Sec-CH-UA-Mobile": "?0",
    "Sec-CH-UA-Platform": "Windows"
}


def fetch_and_save_assets():
    asset_type = args.asset_type
    query = args.query
    querystring = {
        "asset_formats": ["gltf"],
        "currency": "USD",
        "is_ai_generated": "0",
        "is_free": "1",
        "seller": "Quixel",
        "sort_by": "listingTypeWeight",
        "cursor": 0,
        "listing_types": asset_type,
        "q": query
    }
    print(querystring)

    file_path = os.path.join(tempdir, f"output_{asset_type}_{query}.json")

    max_retries = 5  # Number of retries
    retry_delay = 2  # Delay in seconds between retries

    for attempt in range(1, max_retries + 1):
        try:
            # Make the GET request
            # response = requests.get(url, data=payload, headers=headers, params=querystring)
            scraper = cloudscraper.create_scraper()
            response = scraper.get(url, headers=headers, params=querystring)

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


fetch_and_save_assets()








# subprocess.check_call([sys.executable, "-m", "pip", "install", "--upgrade", "pip"])
# subprocess.check_call([sys.executable, "-m", "pip", "install", "certifi"])
# subprocess.check_call([sys.executable, "-m", "pip", "install", "charset-normalizer"])
# subprocess.check_call([sys.executable, "-m", "pip", "install", "idna"])
# subprocess.check_call([sys.executable, "-m", "pip", "install", "requests"])
# subprocess.check_call([sys.executable, "-m", "pip", "install", "urllib3"])
# subprocess.check_call([sys.executable, "-m", "pip", "install", "zstandard"])


# import requests
# # import zstandard as zstd
# import json

#"X-CsrfToken": "l7r17rB8u2gNc7PNMEdFVyo27TvvoQaP",

# url = "https://www.fab.com/i/listings/b69e0ad6-41a4-4f5a-97f4-e438e1b7709d/asset-formats"
# url = "https://www.fab.com/i/listings/dc52417f-58a3-498b-bd02-e7264366d118/asset-formats"
# url = "https://www.fab.com/i/listings/b69e0ad6-41a4-4f5a-97f4-e438e1b7709d/asset-formats/gltf/files/25408c1f-9229-4f06-9a17-413129d1b5f4/download-info/binary"
# url = "https://www.fab.com/i/listings/search"
# url = "https://www.fab.com/i/taxonomy/asset-format-groups"

# Referer = "https://www.fab.com/listings/b69e0ad6-41a4-4f5a-97f4-e438e1b7709d"
# Referer = "https://www.fab.com/listings/dc52417f-58a3-498b-bd02-e7264366d118"
# Referer = "https://www.fab.com/listings/b69e0ad6-41a4-4f5a-97f4-e438e1b7709d"
# Referer = "https://www.fab.com/sellers/Quixel"
# Referer = "https://www.fab.com/sellers/Quixel?is_ai_generated=0&is_free=1&ui_filter_asset_formats=1&asset_formats=gltf&asset_formats=converted-files"


# "listing_types":"3d-model"
# "listing_types":"material",
# "listing_types":"decal",
# "q":"rock"
