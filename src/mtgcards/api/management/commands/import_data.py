import os
from tqdm import tqdm
import urllib.request
import ijson
import functools

from django.core.management.base import BaseCommand, CommandError
import mtgcards.api.utils.scryfall as scryfall
from mtgcards.api.models import Card
from mtgcards.api.models import Image


class Command(BaseCommand):
    help = "import card bulk-data from scryfall"
    suppressed_base_arguments = True

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
        Card.objects.all().delete()

        def create_cards(cards):
            cards_models=[]
            images_models=[]
            for card in cards:
                try:
                    card_model = Card(
                        name=card["name"],
                        collector_number=card["collector_number"],
                        edition=card["set"],
                        image_status=card["image_status"],
                        frame=card["frame"],
                        type_line=scryfall.get_face_type(card),
                        lang=card["lang"],
                        full_art=card["full_art"],
                    )
                    cards_models.append(card_model)
                    images_models.append(
                        Image(
                            card=card_model,
                            url=scryfall.get_face_url(card,"normal"),
                            extension="jpg",
                        ))
                    images_models.append(
                        Image(
                            card=card_model,
                            url=scryfall.get_face_url(card,"png"),
                            extension="png",
                        ),
                    )
                except:
                    print(card["uri"])
                    raise
            Card.objects.bulk_create(objs=cards_models)
            Image.objects.bulk_create(objs=images_models)
            
        buf_size = 6553600
        cards = ijson.sendable_list()
        coro = ijson.items_coro(cards, "item")
        if options["online"]:
            bulk_url, bulk_size = scryfall.get_bulk_url()
            req = urllib.request.Request(
                bulk_url,
                data=None,
                headers={
                    'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_9_3) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/35.0.1916.47 Safari/537.36'
                }
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

        with tqdm(
            total=bulk_size,
            desc=tqdm_desc,
            unit="B",
            unit_scale=True,
        ) as t:
            for chunk in iter(functools.partial(f.read, buf_size), b""):
                coro.send(chunk)
                create_cards(cards)
                del cards[:]
                t.update(buf_size)
            coro.close()
            create_cards(cards)
