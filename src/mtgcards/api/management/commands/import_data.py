import os
from tqdm import tqdm
from urllib.request import urlopen
import ijson
import functools

from django.core.management.base import BaseCommand, CommandError
import mtgcards.api.lib.scryfall as scryfall
from mtgcards.api.models import Card


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
            for card in cards:
                try:
                    card_model = Card(
                        name=card["name"],
                        collector_number=card["collector_number"],
                        edition=card["set"],
                        image_status=card["image_status"],
                        png_url=scryfall.get_face_url(card),
                        frame=card["frame"],
                        type_line=scryfall.get_face_type(card),
                        lang=card["lang"],
                        full_art=card["full_art"],
                    )
                    card_model.save()
                except:
                    print(card["uri"])
                    raise

        buf_size = 65536
        cards = ijson.sendable_list()
        coro = ijson.items_coro(cards, "item")
        if options["online"]:
            buf_size = 65536
            bulk_url, bulk_size = scryfall.get_bulk_url()
            f = urlopen(bulk_url)
            tqdm_desc = "Downloading %s " % bulk_url.split("/")[-1]
        elif options["bulk_file"]:
            buf_size = 65536
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
