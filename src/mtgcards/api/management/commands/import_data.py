import os
from tqdm import tqdm
import urllib.request
import ijson
import functools
from django.db import transaction

from django.core.management.base import BaseCommand, CommandError
from ...utils import scryfall
from ...models import Card
from ...models import Face
from ...models import Image


CARD_UPDATE_FIELDS = [
    "name", "collector_number", "edition", "oracle_id", "scryfall_api_url",
    "image_status", "frame", "lang", "layout", "full_art",
]
FACE_UPDATE_FIELDS = ["name", "side", "type_line", "oracle_text"]


def upsert_cards(cards):
    cards_models = []
    faces_models = []
    images_models = []
    for card in cards:
        if card.get("layout") == "art_series":
            continue
        try:
            card_model = Card(
                scryfall_id=card["id"],
                name=card["name"],
                collector_number=card["collector_number"],
                edition=card["set"],
                oracle_id=scryfall.get_face_oracle(card),
                scryfall_api_url=card["uri"],
                image_status=card["image_status"],
                frame=card["frame"],
                lang=card["lang"],
                full_art=card["full_art"],
                layout=card.get("layout", ""),
            )
            cards_models.append(card_model)

            for i, face_name in enumerate(card["name"].split(" // ")):
                side = "back" if (not card.get("image_uris") and i == 1) else "front"
                face_model = Face(
                    name=face_name,
                    card=card_model,
                    side=side,
                    face_index=i,
                    type_line=scryfall.get_face_type(card, face_name=face_name),
                    oracle_text=scryfall._get_face_data(card, "oracle_text", face_name=face_name),
                )
                faces_models.append(face_model)

                if card["image_status"] not in ["missing", "placeholder"]:
                    images_models.append(Image(
                        url=scryfall.get_face_url(card, face_name=face_name, type="normal"),
                        extension="jpg",
                        face=face_model,
                    ))
                    images_models.append(Image(
                        url=scryfall.get_face_url(card, face_name=face_name, type="png"),
                        extension="png",
                        face=face_model,
                    ))
        except:
            print(card["uri"])
            raise

    with transaction.atomic():
        Card.objects.bulk_create(
            objs=cards_models,
            batch_size=1000,
            update_conflicts=True,
            update_fields=CARD_UPDATE_FIELDS,
            unique_fields=["scryfall_id"],
        )
        Face.objects.bulk_create(
            objs=faces_models,
            batch_size=1000,
            update_conflicts=True,
            update_fields=FACE_UPDATE_FIELDS,
            unique_fields=["card", "face_index"],
        )

        # Fetch existing image URLs so we can detect URL changes
        face_pks = [f.pk for f in faces_models]
        existing_urls = {
            (row["face_id"], row["extension"]): row["url"]
            for row in Image.objects.filter(face_id__in=face_pks).values("face_id", "extension", "url")
        }

        # Images whose URL changed (or are new) need bluriness/size/image reset.
        # Unchanged images are skipped entirely — nothing to update.
        images_to_upsert = [
            img for img in images_models
            if (img.face.pk, img.extension) not in existing_urls
            or existing_urls[(img.face.pk, img.extension)] != img.url
        ]
        if images_to_upsert:
            Image.objects.bulk_create(
                objs=images_to_upsert,
                batch_size=1000,
                update_conflicts=True,
                update_fields=["url", "bluriness", "size", "image"],
                unique_fields=["face", "extension"],
            )


class Command(BaseCommand):
    help = "import card bulk-data from scryfall"

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

        cards_deleted = 0
        for migration in scryfall.get_migrations():
            to_delete = Card.objects.filter(scryfall_id=migration["old_scryfall_id"])
            cards_deleted += len(to_delete)
            to_delete.delete()
        if cards_deleted > 0:
            self.stdout.write(self.style.SUCCESS('Successfully deleted %i deprecated cards.' % cards_deleted))
        else:
            self.stdout.write(self.style.SUCCESS('No deprecated cards to delete.'))

        cards = ijson.sendable_list()
        coro = ijson.items_coro(cards, "item")
        with tqdm(
            total=bulk_size,
            desc=tqdm_desc,
            unit="B",
            unit_scale=True,
        ) as t:
            for chunk in iter(functools.partial(f.read, buf_size), b""):
                coro.send(chunk)
                if len(cards) > 800:
                    upsert_cards(cards)
                    del cards[:]
                t.update(buf_size)
            coro.close()

        upsert_cards(cards)

        self.stdout.write(self.style.SUCCESS('Import complete.'))
