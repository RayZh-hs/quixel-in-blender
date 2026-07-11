import argparse
import json
import os
import sys
import time
from PIL import Image
import cloudscraper
import platform

# Set user agent depending on OS
if platform.system() == 'Windows':
    user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:140.0) Gecko/20100101 Firefox/140.0"
else:
    user_agent = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36"

headers = {
    "Accept": "application/json, text/plain, */*",
    # Only advertise encodings requests can actually decode. The venv ships no
    # brotli decoder, so advertising "br" makes Cloudflare return brotli-compressed
    # bodies that come back as undecodable bytes and break response.json().
    "Accept-Encoding": "gzip, deflate",
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

# Fab renamed the Quixel storefront: the old "Quixel" seller slug now returns
# zero results. Free Megascans assets are published under "Quixel Megascans"
# (plants live under a separate "Quixel Megaplants" seller, intentionally excluded).
QUIXEL_SELLER = "Quixel Megascans"

querystring = {
    "is_free": "1",
    "seller": QUIXEL_SELLER,
    "sort_by": "-firstPublishedAt"  # Default sort
}


def _linux_chrome_safe_storage_key():
    """Fetch Chrome's 'Chrome Safe Storage' key by attribute, the way
    `secret-tool lookup application chrome` does.

    pycookiecheat's default keyring lookup grabs the wrong item on KDE/ksecretd
    (which exposes several similarly named 'Chrome Safe Storage' entries), so it
    derives a bad AES key and decryption yields garbage. Resolving the secret
    ourselves and handing it to chrome_cookies(password=...) sidesteps that.
    Returns the secret bytes, or None to let pycookiecheat use its default path.
    """
    try:
        import secretstorage
        conn = secretstorage.dbus_init()
        collection = secretstorage.get_default_collection(conn)
        for item in collection.search_items({"application": "chrome"}):
            return item.get_secret()
    except Exception:
        print(str(sys.exc_info()))
    return None


def get_cookies():
    """Read the user's logged-in fab.com session cookies from their browser."""
    try:
        from pycookiecheat import firefox_cookies, chrome_cookies
    except Exception:
        print(str(sys.exc_info()))
        return {}

    all_cookies = {}
    # Chrome first. On Linux, pass the key explicitly so KDE keyring ambiguity
    # (and modern Chrome's v11 / db-v24 cookie encryption) doesn't break us.
    try:
        password = _linux_chrome_safe_storage_key() if platform.system() == "Linux" else None
        all_cookies = chrome_cookies("https://www.fab.com", password=password) or {}
    except Exception:
        print(str(sys.exc_info()))

    # Fall back to Firefox if Chrome yielded no session.
    if not all_cookies.get("fab_sessionid"):
        try:
            all_cookies = firefox_cookies("https://www.fab.com") or all_cookies
        except Exception:
            print(str(sys.exc_info()))

    session_id = all_cookies.get("fab_sessionid", "")
    csrftoken = all_cookies.get("fab_csrftoken", "")
    if session_id or csrftoken:
        return {'fab_sessionid': session_id, 'fab_csrftoken': csrftoken}
    return {}


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


def smart_square_crop(image_path, border_width=40):
    image = Image.open(image_path).convert("RGB")
    width, height = image.size
    target_color = (32, 32, 32)
    pixels = image.load()

    top, bottom, left, right = 0, height, 0, width

    # Scan from top
    for y in range(height):
        if any(pixels[x, y] != target_color for x in range(width)):
            top = y
            break

    # Scan from bottom
    for y in range(height - 1, -1, -1):
        if any(pixels[x, y] != target_color for x in range(width)):
            bottom = y + 1
            break

    # Scan from left
    for x in range(width):
        if any(pixels[x, y] != target_color for y in range(height)):
            left = x
            break

    # Scan from right
    for x in range(width - 1, -1, -1):
        if any(pixels[x, y] != target_color for y in range(height)):
            right = x + 1
            break

    # Apply border
    top = max(0, top - border_width)
    bottom = min(height, bottom + border_width)
    left = max(0, left - border_width)
    right = min(width, right + border_width)

    cropped_width = right - left
    cropped_height = bottom - top
    new_size = max(cropped_width, cropped_height)
    left_offset = (new_size - cropped_width) // 2
    top_offset = (new_size - cropped_height) // 2

    # Create a new square image with the target color
    new_image = Image.new("RGB", (new_size, new_size), target_color)
    cropped = image.crop((left, top, right, bottom))
    new_image.paste(cropped, (left_offset, top_offset))

    new_image.save(image_path)


def fetch_assets(url, referer, data_dir, asset_type=None, query=None, cursor=None, sort_method=None):
    headers["Referer"] = referer
    querystring["cursor"] = cursor
    querystring["listing_types"] = asset_type
    if asset_type == "3d-model":
        querystring["asset_formats"] = "fbx"
    if asset_type == "material":
        querystring["asset_formats"] = "texture-set"
    querystring["q"] = query

    # Map sort_method to the appropriate API sort_by parameter
    sort_mapping = {
        'newest': '-firstPublishedAt',
        'oldest': 'firstPublishedAt',
        'title_asc': 'title',
        'title_desc': '-title'
    }
    querystring["sort_by"] = sort_mapping.get(sort_method, '-firstPublishedAt')

    file_path = os.path.join(data_dir, f"search_{asset_type}_{query}_{sort_method}_{cursor}.json")

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
    scraper = cloudscraper.create_scraper(browser={'custom': headers["User-Agent"]})
    cookies = get_cookies()
    print(cookies)

    for attempt in range(1, max_retries + 1):
        try:
            # Make the GET request
            if query:
                response = scraper.get(url, headers=headers, params=query, cookies=cookies)
            else:
                response = scraper.get(url, headers=headers, cookies=cookies)

            if response.status_code == 200:
                # Success: Process the response
                try:
                    json_data = response.json()
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
                # A 403 is either a transient Cloudflare block (worth retrying) or a hard
                # auth error like {"detail": "Must be logged in to download ..."}. The latter
                # will never succeed on retry, so bail out early with a clear message instead
                # of burning through all the attempts and leaving no output file behind.
                detail = ""
                try:
                    detail = response.json().get("detail", "")
                except Exception:
                    pass
                if detail:
                    print(f"AUTH ERROR: {detail} — log into fab.com in Chrome or Firefox "
                          f"so the addon can read your session cookies.")
                    return
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
    elif function_name == "smart_square_crop":
        smart_square_crop(*args)
    else:
        print("Function not found")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--function", required=True, help="Name of the function to run")
    parser.add_argument("args", nargs=argparse.REMAINDER, help="Arguments for the function")
    args = parser.parse_args()
    main(args.function, *args.args)

