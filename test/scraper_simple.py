import platform
import cloudscraper

# url = "https://www.fab.com/i/listings/search"
# referer = "https://www.fab.com/sellers/Quixel"
url = "https://www.fab.com/i/listings/18e5810e-ca6a-4129-be9a-7dc6fe08bc4d/asset-formats/fbx/files/f95bcdbc-3dea-4604-b67c-244af3c679c4/download-info/binary"
referer = "https://www.fab.com/i/listings/18e5810e-ca6a-4129-be9a-7dc6fe08bc4d"

if platform.system() == 'Windows':
    user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:140.0) Gecko/20100101 Firefox/140.0"
else:
    user_agent = "Mozilla/5.0 (X11; Linux x86_64; rv:140.0) Gecko/20100101 Firefox/140.0"

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

# Use cloudscraper to bypass Cloudflare challenges
scraper = cloudscraper.create_scraper()
response = scraper.get(url, headers=headers)

# Print the status code and response
print("Status Code:", response.status_code)
# print("Response Content:", response.content.decode('utf-8'))








# import requests
# import logging
#
# import http.client
# http.client.HTTPConnection.debuglevel = 1
#
# logging.basicConfig(level=logging.DEBUG)
#
# url = "https://www.fab.com/i/listings/search"
# # url = "https://www.fab.com/i/listings/b02cdcb8-a5e8-4e96-8fec-60b5a0c31a9f/asset-formats"
# # url = "https://www.fab.com/i/listings/b02cdcb8-a5e8-4e96-8fec-60b5a0c31a9f/asset-formats/gltf/files/0b564456-22d7-44bb-aa1d-6c80b16912f7/download-info/binary"
#
# Referer = "https://www.fab.com/sellers/Quixel"
# # Referer = "https://www.fab.com/i/listings/b02cdcb8-a5e8-4e96-8fec-60b5a0c31a9f"
#
# # "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:134.0) Gecko/20100101 Firefox/134.0"
# # "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36"
# # "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36 Edg/132.0.0.0"
# # "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:134.0) Gecko/20100101 Firefox/134.0"
#
# headers = {
#     "Accept": "application/json, text/plain, */*",
#     "Accept-Encoding": "gzip, deflate, br, zstd",
#     "Accept-Language": "en",
#     "Alt-Used": "www.fab.com",
#     "Connection": "keep-alive",
#     "Dnt": "1",
#     "Referer": Referer,
#     "Sec-Fetch-Dest": "empty",
#     "Sec-Fetch-Mode": "cors",
#     "Sec-Fetch-Site": "same-origin",
#     "Sec-Gpc": "1",
#     "User-Agent": "Mozilla/5.0 (X11; Linux x86_64; rv:134.0) Gecko/20100101 Firefox/134.0",
#     "X-Requested-With": "XMLHttpRequest"
# }
#
# response = requests.get(url, headers=headers)
#
# print(response.status_code)
#