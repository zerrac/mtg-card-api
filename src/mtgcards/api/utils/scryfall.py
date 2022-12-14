import threading
import time
import requests
from requests.adapters import HTTPAdapter, Retry
import os.path
import shutil
import sys


class Throttle:
    def __init__(self, delay: float = 0.05):
        self.delay = delay
        self.lock = threading.Lock()
        self.time = 0

    def __enter__(self):
        with self.lock:
            if self.time + self.delay > time.time():
                time.sleep(self.time + self.delay - time.time())
            self.time = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


rate_limiter = Throttle()
SCRYFALL_URL = "https://api.scryfall.com"

http = requests.Session()
retries = Retry(total=5, status_forcelist=[429, 500, 502, 503, 504])

http.mount("http://", HTTPAdapter(max_retries=retries))
http.mount("https://", HTTPAdapter(max_retries=retries))


def image_getsize(url):
    with rate_limiter:
        re = http.head(url)
    re.raise_for_status()
    if "Content-Length" in re.headers.keys():
        return int(re.headers["Content-Length"])
    else:
        return 0


def get_data(url):
    with rate_limiter:
        re = http.get(url)
    re.raise_for_status()
    data = re.json()["data"]

    if re.json()["has_more"]:
        data = data + get_data(re.json()["next_page"])

    return data


def get_bulk_url(database_type="all_cards"):
    databases = get_data(SCRYFALL_URL + "/bulk-data")
    online_db = []
    for database in databases:
        if database["type"] == database_type:
            online_db = database
            break
    if "compressed_size" in online_db:
        size = online_db["compressed_size"]
    elif "size" in online_db:
        size = online_db["size"]
    else:
        size = 0
    return online_db["download_uri"], size

def get_migrations():
    return get_data(SCRYFALL_URL + "/migrations")

def get_face_url(card, face_name=None, type="png"):
    return _get_face_data(card, field="image_uris", face_name=face_name)[type]


def get_face_oracle(card):
    return _get_face_data(card, field="oracle_id", face_name=None)


def get_face_type(card, face_name=None):
    return _get_face_data(card, field="type_line", face_name=face_name)


def _get_face_data(card, field, face_name=None):
    if field in card:
        return card[field]
    elif "card_faces" in card:
        if face_name != None:
            for card_face in card["card_faces"]:
                if card_face["name"] == face_name:
                    return card_face[field]
        else:
            return card["card_faces"][0][field]
