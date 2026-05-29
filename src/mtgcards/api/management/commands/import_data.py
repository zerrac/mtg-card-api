import os
from tqdm import tqdm
import urllib.request
import ijson
import functools
from django.db import connection, transaction

from django.core.management.base import BaseCommand, CommandError
from ...utils import scryfall
from ...models import Card, Face, Image


def _build_models(cards):
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
    return cards_models, faces_models, images_models


def insert_batch(cards):
    cards_models, faces_models, images_models = _build_models(cards)
    if not cards_models:
        return 0
    with transaction.atomic():
        Card.objects.bulk_create(objs=cards_models, batch_size=1000)
        for face in faces_models:
            face.card_id = face.card.pk
        Face.objects.bulk_create(objs=faces_models, batch_size=1000)
        for img in images_models:
            img.face_id = img.face.pk
        Image.objects.bulk_create(objs=images_models, batch_size=1000)
    return len(cards_models)


def backfill_blur():
    with connection.cursor() as cursor:
        cursor.execute("""
            UPDATE api_image AS i
            SET bluriness = bc.bluriness,
                image     = bc.image_key
            FROM api_blurcache AS bc
            JOIN api_face AS f ON f.id = i.face_id
            JOIN api_card AS c ON c.id = f.card_id
            WHERE c.scryfall_id = bc.scryfall_id
              AND f.face_index  = bc.face_index
              AND i.extension   = bc.extension
              AND bc.bluriness  > 0
        """)
        return cursor.rowcount


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
        if cards_deleted:
            self.stdout.write(self.style.SUCCESS('Deleted %i deprecated cards.' % cards_deleted))

        self.stdout.write('Truncating cards...')
        Card.objects.all().delete()

        cards = ijson.sendable_list()
        cards_imported = 0
        coro = ijson.items_coro(cards, "item")
        with tqdm(total=bulk_size, desc=tqdm_desc, unit="B", unit_scale=True) as t:
            for chunk in iter(functools.partial(f.read, buf_size), b""):
                coro.send(chunk)
                if len(cards) > 800:
                    cards_imported += insert_batch(cards)
                    del cards[:]
                t.update(buf_size)
            coro.close()

        cards_imported += insert_batch(cards)

        self.stdout.write('Restoring bluriness from cache...')
        restored = backfill_blur()

        self.stdout.write(self.style.SUCCESS(
            'Imported %i cards, restored bluriness for %i images.' % (cards_imported, restored)
        ))
