import os
from tqdm import tqdm
import urllib.request
import ijson
import functools
from django.db import models

from django.core.management.base import BaseCommand, CommandError
from ...utils import scryfall
from ...models import Card
from ...models import Face
from ...models import Image


def create_cards(cards):
    cards_models = []
    faces_models = []
    images_models = []
    for card in cards:
        try:
            card_data = {
                "scryfall_id": card["id"],
                "name": card["name"],
                "collector_number": card["collector_number"],
                "edition": card["set"],
                "oracle_id": scryfall.get_face_oracle(card),
                "scryfall_api_url": card["uri"],
                "image_status": card["image_status"],
                "frame": card["frame"],
                "lang": card["lang"],
                "full_art": card["full_art"],
            }

            card_model = Card(**card_data)
            cards_models.append(card_model)

            i = 0
            for face_name in card["name"].split(" // "):
                if not "image_uris" in card and i == 1:
                    side = "back"
                else:
                    side = "front"
                i += 1
                face_data = {
                    "name": face_name,
                    "card": card_model,
                    "side": side,
                    "type_line": scryfall.get_face_type(card, face_name=face_name),
                    "oracle_text": scryfall._get_face_data(
                        card, "oracle_text", face_name=face_name
                    ),
                }
                face_model = Face(**face_data)
                faces_models.append(face_model)

                if not card["image_status"] in ["missing","placeholder"]:
                    image_data = {
                        "url": scryfall.get_face_url(
                            card, face_name=face_name, type="normal"
                        ),
                        "extension": "jpg",
                        "face": face_model,
                    }
                    images_models.append(Image(**image_data))
                    image_data = {
                        "url": scryfall.get_face_url(card, face_name=face_name, type="png"),
                        "extension": "png",
                        "face": face_model,
                    }
                    images_models.append(Image(**image_data))
        except:
            print(card["uri"])
            raise

    Card.objects.bulk_create(
        objs=cards_models,
        batch_size=1000,
    )
    Face.objects.bulk_create(
        objs=faces_models,
        batch_size=1000,
    )
    Image.objects.bulk_create(
        objs=images_models,
        batch_size=1000,
    )

class Command(BaseCommand):
    help = "import card bulk-data from scryfall"
    # suppressed_base_arguments = True

    def add_arguments(self, parser):
        parser.add_argument(
            "--bulk-file",
            dest="bulk_file",
            help="Path to the bulk file downloaded from scryfall",
        )
        parser.add_argument(
            "--online",
            action="store_true",
            help="Automatically download last version of bulk data online",
        )

    def handle(self, *args, **options):
        if options["online"]:
            bulk_url, bulk_size = scryfall.get_bulk_url()
            req = urllib.request.Request(
                bulk_url,
                data=None,
                headers={
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_9_3) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/35.0.1916.47 Safari/537.36"
                },
            )
            f = urllib.request.urlopen(req)
            tqdm_desc = "Downloading %s " % bulk_url.split("/")[-1]
        elif options["bulk_file"]:
            f = open(options["bulk_file"], "rb")
            bulk_size = os.path.getsize(options["bulk_file"])
            tqdm_desc = "Loading %s " % os.path.basename(options["bulk_file"])
        else:
            raise CommandError(
                "import must either be online or you must specify a local bulk file"
            )

        buf_size = 655360
        existing_scryfall_id = set([card.scryfall_id for card in Card.objects.all()])
        cards = ijson.sendable_list()
        cards_created = 0
        coro = ijson.items_coro(cards, "item")
        with tqdm(
            total=bulk_size,
            desc=tqdm_desc,
            unit="B",
            unit_scale=True,
        ) as t:
            for chunk in iter(functools.partial(f.read, buf_size), b""):
                coro.send(chunk)
                if len(cards)>800:
                    # create cards by batch of 800 during bulk file reading
                    to_create = [card for card in cards if not card["id"] in existing_scryfall_id]
                    cards_created += len(to_create)
                    create_cards(to_create)
                    del cards[:]
                t.update(buf_size)
            coro.close()
        
        # create the remaining cards
        to_create = [card for card in cards if not card["id"] in existing_scryfall_id]
        cards_created += len(to_create)
        create_cards(to_create)
        
        
        
        if cards_created > 0:
            self.stdout.write(self.style.SUCCESS('Successfully imported %i new cards.' % cards_created))
        else:
            self.stdout.write(self.style.SUCCESS('No new cards to import'))

        cards_deleted = 0
        for migrations in scryfall.get_migrations():
            to_delete=Card.objects.filter(scryfall_id=migrations["old_scryfall_id"])
            cards_deleted += len(to_delete)
            to_delete.delete()
        if cards_deleted > 0:
            self.stdout.write(self.style.SUCCESS('Successfully deleted %i deprecated cards.' % cards_created))
        else:
            self.stdout.write(self.style.SUCCESS('No deprecated cards to delete.'))
