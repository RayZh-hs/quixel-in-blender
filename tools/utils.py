import argparse
import json
import os
import time
from PIL import Image
import cloudscraper
import platform


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

querystring = {
    "asset_formats": ["gltf"],
    "currency": "USD",
    "is_ai_generated": "0",
    "is_free": "1",
    "seller": "Quixel",
    "sort_by": "listingTypeWeight"
}

# data_dir = "/tmp/fab_data"

# if not os.path.exists(data_dir):
#     os.mkdir(data_dir)


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


def fetch_assets(url, referer, data_dir, asset_type=None, query=None, cursor=None):
    headers["Referer"] = referer
    querystring["cursor"] = cursor
    querystring["listing_types"] = asset_type
    querystring["q"] = query

    file_path = os.path.join(data_dir, f"search_{asset_type}_{query}_{cursor}.json")

    fetcher(url, headers, file_path, query=querystring)


def fetch_asset_formats(url, referer, data_dir, asset_uid=None):
    headers["Referer"] = referer
    file_path = os.path.join(data_dir, f"asset_{asset_uid}.json")

    fetcher(url, headers, file_path)


def fetch_down_link(url, referer, data_dir, asset_uid=None):
    headers["Referer"] = referer
    file_path = os.path.join(data_dir, f"downlink_{asset_uid}.json")

    fetcher(url, headers, file_path)


def fetcher(url, header, file_path, query=None):
    max_retries = 5  # Number of retries
    retry_delay = 2  # Delay in seconds between retries
    # Create the cloudscraper instance
    scraper = cloudscraper.create_scraper()

    for attempt in range(1, max_retries + 1):
        try:
            # Make the GET request
            if query:
                # response = requests.get(url, headers=header, params=query)
                response = scraper.get(url, headers=headers, params=query)
            else:
                # response = requests.get(url, headers=header)
                response = scraper.get(url, headers=headers)

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

        except cloudscraper.exceptions.CloudflareChallengeError as e:
            print(f"Attempt {attempt}: Cloudflare challenge failed: {e}. Retrying in {retry_delay} seconds...")
            time.sleep(retry_delay)
            continue

        except cloudscraper.exceptions.CloudflareCaptchaError as e:
            print(f"Attempt {attempt}: Cloudflare CAPTCHA required: {e}. Unable to proceed.")
            return

        except Exception as e:
            print(f"Attempt {attempt}: Request failed with exception: {e}. Retrying in {retry_delay} seconds...")
            time.sleep(retry_delay)
            continue

    print("All retry attempts failed. Exiting.")


def download_file(url, out_file):
    print("Downloading file...")
    # Create the cloudscraper instance
    scraper = cloudscraper.create_scraper()
    # response = requests.get(url, stream=True)
    response = scraper.get(url, stream=True)
    response.raise_for_status()

    total_size = int(response.headers.get('content-length', 0))
    downloaded_size = 0

    # Determine chunk size dynamically
    if total_size < 1_000_000:  # Less than 1 MB
        chunk_size = 8192  # 8 KB
    elif total_size < 100_000_000:  # 1 MB to 100 MB
        chunk_size = 65536  # 64 KB
    else:  # Greater than 100 MB
        chunk_size = 262144  # 256 KB

    with open(out_file, 'wb') as file:
        for chunk in response.iter_content(chunk_size=chunk_size):
            file.write(chunk)
            downloaded_size += len(chunk)
            if total_size > 0:
                progress = (downloaded_size / total_size) * 100
                print(f"Download Progress: {progress:.2f}%")
            else:
                print("Download Progress: Unknown file size")

    print(f"File downloaded successfully and saved as '{out_file}'.")


def main(function_name, *args):
    if function_name == "crop_thumbnails":
        crop_thumbnails(*args)
    elif function_name == "fetch_assets":
        fetch_assets(*args)
    elif function_name == "fetch_asset_formats":
        fetch_asset_formats(*args)
    elif function_name == "fetch_down_link":
        fetch_down_link(*args)
    elif function_name == "download_file":
        download_file(*args)
    else:
        print("Function not found")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--function", required=True, help="Name of the function to run")
    parser.add_argument("args", nargs=argparse.REMAINDER, help="Arguments for the function")
    args = parser.parse_args()
    main(args.function, *args.args)

