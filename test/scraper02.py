import sys
import os
import subprocess
import argparse
import time
import platform
import cloudscraper
import json
import tempfile
from bs4 import BeautifulSoup

tempdir = tempfile.gettempdir()

# url = "https://www.fab.com/i/listings/search"
url = "https://www.fab.com/sellers/Quixel"
# referer = "https://www.fab.com/sellers/Quixel"

if platform.system() == 'Windows':
    user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:135.0) Gecko/20100101 Firefox/135.0"
else:
    user_agent = "Mozilla/5.0 (X11; Linux x86_64; rv:135.0) Gecko/20100101 Firefox/135.0"

headers = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Encoding": "gzip, deflate, br, zstd",
    "Accept-Language": "en",
    "Alt-Used": "www.fab.com",
    "Connection": "keep-alive",
    "Dnt": "1",
    # "Referer": referer,
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
    # querystring = {"aggregate_on": "category_per_listing_type", "count": "0", "currency": "USD", "seller": "Quixel"}
    #
    # print(querystring)

    file_path = os.path.join(tempdir, f"output_listing_tree.json")

    max_retries = 5  # Number of retries
    retry_delay = 2  # Delay in seconds between retries

    for attempt in range(1, max_retries + 1):
        try:
            # Make the GET request
            # response = requests.get(url, data=payload, headers=headers, params=querystring)
            scraper = cloudscraper.create_scraper()
            # response = scraper.get(url, headers=headers, params=querystring)
            response = scraper.get(url, headers=headers)

            if response.status_code == 200:
                # Success: Process the response
                # try:
                    # json_response = response.content.decode('utf-8')  # Decode without decompression
                    # json_data = json.loads(json_response)  # Parse the decoded data as JSON

                soup = BeautifulSoup(response.text, "html.parser")
                script_tag = soup.find("script", id="js-json-data-prefetched-data", type="application/json")

                if script_tag:
                    json_text = script_tag.string.strip()
                    json_data = json.loads(json_text)

                    # Extract only the "/i/taxonomy/categories/tree": { "results": ... } part
                    extracted_data = json_data.get("/i/taxonomy/categories/tree", {}).get("results", {})

                    pretty_json = json.dumps(extracted_data, indent=2)
                    with open(file_path, 'w') as f:
                        f.write(pretty_json)

                    print(f"Data saved to {file_path}")
                    return  # Success
                else:
                    print("JSON script tag not found on the page.")
                    return

                # except ValueError:
                #     print("Decoded content is not in valid JSON format.")
                #     return  # Exit the function if content is invalid

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




