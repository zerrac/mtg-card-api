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


    def __exit__(self,exc_type, exc_val, exc_tb):
        pass

rate_limiter = Throttle()
SCRYFALL_URL="https://api.scryfall.com"

http = requests.Session()
retries = Retry(total=5,
                status_forcelist=[ 429, 500, 502, 503, 504])

http.mount('http://', HTTPAdapter(max_retries=retries))
http.mount('https://', HTTPAdapter(max_retries=retries))

def image_getsize(url):
    with rate_limiter:
        re =  http.head(url)
    re.raise_for_status()
    if 'Content-Length' in re.headers.keys():
        return int(re.headers['Content-Length'])
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
    databases = get_data(SCRYFALL_URL+"/bulk-data")
    online_db = []
    for database in databases:
        if database["type"] == database_type:
            online_db = database
            break
    return online_db["download_uri"], online_db["compressed_size"]

def get_face_url(card,type="png"):
    if card["image_status"] == "missing":
        return "missing"
    if 'image_uris' in card:
        return card['image_uris'][type]
    elif 'card_faces' in card:
        return  card['card_faces'][0]['image_uris'][type]
    

def get_face_type(card):
    if 'type_line' in card:
        return card['type_line']
    elif 'card_faces' in card:
        return  card['card_faces'][0]['type_line']