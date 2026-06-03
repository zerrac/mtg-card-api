import time

from django.core.management.base import BaseCommand
from django.db.models import Count

from ...models import Card
from .seed_popular_cards import _select_bulk

SIDES = ["front", "back"]


class Command(BaseCommand):
    help = "Pre-seed R2 with the best images for cards with many prints"

    def add_arguments(self, parser):
        parser.add_argument(
            "--min-prints",
            type=int,
            default=80,
            dest="min_prints",
            help="Minimum number of prints for a card to be seeded (default: 80)",
        )
        parser.add_argument(
            "--extension",
            default="png",
            help="Image extension to seed (default: png)",
        )
        parser.add_argument(
            "--langs",
            nargs="+",
            default=["en", "fr"],
            help="Languages to seed (default: en fr)",
        )

    def handle(self, *args, **options):
        min_prints = options["min_prints"]
        extension = options["extension"]
        langs = options["langs"]

        oracle_ids = list(
            Card.objects.values("oracle_id")
            .annotate(n=Count("id"))
            .filter(n__gte=min_prints)
            .values_list("oracle_id", flat=True)
        )

        found = len(oracle_ids)
        self.stdout.write(
            "Found %d oracle_ids with ≥%d prints (langs: %s, ext: %s)"
            % (found, min_prints, " ".join(langs), extension)
        )

        self.stdout.write(
            "Phase 1: selecting best images (%d oracle_ids × %d langs × %d sides)..."
            % (found, len(langs), len(SIDES))
        )

        selected_images = []
        errors = 0
        t0 = time.monotonic()

        for lang in langs:
            for side in SIDES:
                imgs, errs = _select_bulk(oracle_ids, lang, side, extension)
                selected_images.extend(imgs)
                errors += errs

        elapsed = time.monotonic() - t0
        self.stdout.write(
            "  Phase 1 done in %.1fs — %d images to upload" % (elapsed, len(selected_images))
        )

        self.stdout.write(
            "Phase 2: uploading %d selected images to R2..." % len(selected_images)
        )

        total2 = len(selected_images)
        step2 = max(1, total2 // 20)
        t1 = time.monotonic()
        for i, image in enumerate(selected_images, 1):
            try:
                image.download(store=True)
            except Exception as e:
                self.stderr.write("Error storing %s: %s" % (image.url, e))
                errors += 1
            if i % step2 == 0 or i == total2:
                elapsed = time.monotonic() - t1
                rate = i / elapsed if elapsed else 0
                self.stdout.write(
                    "  Phase 2: %d/%d (%d%%) — %.1f img/s"
                    % (i, total2, 100 * i // total2, rate)
                )

        self.stdout.write(
            self.style.SUCCESS("Done. %d errors total." % errors)
        )
