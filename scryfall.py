import threading
import time
import requests
from requests.adapters import HTTPAdapter, Retry
import shutil
import sys
import os
from pathlib import Path
from tempfile import gettempdir
from functools import lru_cache
import json
from tqdm import tqdm
from collections import defaultdict


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

scryfall_temp = Path("./tmp/scryfall_temp")
scryfall_temp.mkdir(parents=True, exist_ok=True)
db_loading_lock = threading.Lock()


def get_data(url):
    with rate_limiter:
        re = http.get(url)
    re.raise_for_status()
    data = re.json()["data"]

    if re.json()["has_more"]:
        data = data + get_data(re.json()["next_page"])

    return data


def download(url, dest, size=None):
    with rate_limiter:
        re = http.get(url, stream=True)
    re.raise_for_status()
    file_size = size or int(req.headers["Content-Length"])
    chunk_size = 1024
    with open(dest, "xb") as f, tqdm(
        total=file_size,
        desc="Downloading %s " % url.split("/")[-1],
        unit="B",
        unit_scale=True,
    ) as t:
        for chunk in re.iter_content(chunk_size=chunk_size):
            if chunk:
                f.write(chunk)
                t.update(chunk_size)


def get_cards(**kwargs):
    """Get all cards matching certain attributes.

    Matching is case insensitive.

    Args:
        kwargs: (key, value) pairs, e.g. `name="Tendershoot Dryad", set="RIX"`.
                keys with a `None` value are ignored

    Returns:
        List of all matching cards
    """
    cards = _get_database()

    for key, value in kwargs.items():
        if value is not None:
            value = value.lower()
            if key == "name":  # Normalize card name
                value = value.replace("æ", "ae")
            cards = [
                card for card in cards if key in card and card[key].lower() == value
            ]

    return cards


def get_card(card_name: str, set_id: str = None, collector_number: str = None):
    """Find a card by it's name and possibly set and collector number.

    In case, the Scryfall database contains multiple cards, the first is returned.

    Args:
        card_name: Exact English card name
        set_id: Shorthand set name
        collector_number: Collector number, may be a string for e.g. promo suffixes

    Returns:
        card: Dictionary of card, or `None` if not found.
    """
    cards = get_cards(name=card_name, set=set_id, collector_number=collector_number)

    return cards[0] if len(cards) > 0 else None


@lru_cache(maxsize=None)
def cards_by_oracle_id():
    """Create dictionary to look up cards by their oracle id.

    Faster than repeated lookup via get_cards().

    Returns:
        dict {id: [cards]}
    """
    cards_by_oracle_id = defaultdict(list)
    for c in get_cards():
        if "oracle_id" in c:  # Not all cards have a oracle id, *sigh*
            cards_by_oracle_id[c["oracle_id"]].append(c)
    return cards_by_oracle_id


@lru_cache(maxsize=None)
def _get_database():
    with db_loading_lock:
        databases = get_data("https://api.scryfall.com/bulk-data")
        online_db = []
        for database in databases:
            if database["type"] == "all_cards":
                online_db = database
                break
        online_db_name = online_db["download_uri"].split("/")[-1]
        online_db_size = online_db["compressed_size"]
        local_db_names = os.listdir(scryfall_temp)

        dest = scryfall_temp / online_db_name
        if (
            len(local_db_names) == 0
            or (not online_db_name in local_db_names)
            or os.path.getsize(dest) < online_db_size
        ):
            for local_file in local_db_names:
                os.remove(scryfall_temp / local_file)
            download(online_db["download_uri"], dest=dest, size=online_db_size)
        else:
            print("Réutilisation de la DB %s" % dest)

        with open(dest, "r", encoding="utf-8") as f:
            return json.load(f)


def evaluate_card_score(card, preferred_lang="fr"):
    score = 0
    if card["lang"] == preferred_lang:
        score += 200
    elif card["lang"] == "en":
        score += 100

    if card["collector_number"].isnumeric():
        score += 80

    if (
        "type_line" in card
        and card["type_line"].lower().startswith("basic land")
        and card["full_art"]
    ):
        score += 50

    if card["frame"] == "2015":
        score += 40

    if card["set"] != "sld":
        score += 10

    if card["image_status"] == "highres_scan":
        score += 2
    elif card["image_status"] == "lowres":
        score += 1

    return score


def init_db():

    thread = threading.Thread(target=_get_database, args=())
    thread.setDaemon(True)  # Daemonize thread
    thread.start()  # Start the execution
