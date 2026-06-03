from django.core.management.base import BaseCommand
from django.db.models import Count, Max
from tqdm import tqdm

from ...models import Card, Image


class Command(BaseCommand):
    help = "Pre-compute bluriness scores for cards with many prints, storing only the sharpest per lang to S3"

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

        busy_oracle_ids = list(
            Card.objects.values("oracle_id")
            .annotate(n=Count("id"))
            .filter(n__gte=min_prints)
            .values_list("oracle_id", flat=True)
        )

        images_qs = (
            Image.objects.filter(
                face__card__oracle_id__in=busy_oracle_ids,
                extension=extension,
                bluriness=0,
                face__card__lang__in=langs,
            )
            .exclude(face__card__image_status__in=["placeholder", "missing"])
            .select_related("face__card")
        )

        total = images_qs.count()
        self.stdout.write(
            "Phase 1: measuring bluriness for %d images (no S3 upload)..." % total
        )

        errors = 0
        with tqdm(total=total, unit="img") as t:
            for image in images_qs.iterator():
                try:
                    image.download(store=False)
                except Exception as e:
                    self.stderr.write("Error measuring %s: %s" % (image.url, e))
                    errors += 1
                t.update(1)

        # Find best image (highest bluriness) per (oracle_id, lang, face_index)
        groups = (
            Image.objects.filter(
                face__card__oracle_id__in=busy_oracle_ids,
                extension=extension,
                face__card__lang__in=langs,
            )
            .exclude(face__card__image_status__in=["placeholder", "missing"])
            .values("face__card__oracle_id", "face__card__lang", "face__face_index")
            .annotate(max_blur=Max("bluriness"))
        )

        best_pks = []
        for group in groups:
            img = (
                Image.objects.filter(
                    face__card__oracle_id=group["face__card__oracle_id"],
                    face__card__lang=group["face__card__lang"],
                    face__face_index=group["face__face_index"],
                    extension=extension,
                    bluriness=group["max_blur"],
                )
                .select_related("face__card")
                .first()
            )
            if img:
                best_pks.append(img.pk)

        self.stdout.write(
            "Phase 2: uploading %d best images to S3..." % len(best_pks)
        )

        with tqdm(total=len(best_pks), unit="img") as t:
            for img in Image.objects.filter(pk__in=best_pks).select_related("face__card"):
                try:
                    img.download(store=True)
                except Exception as e:
                    self.stderr.write("Error storing %s: %s" % (img.url, e))
                    errors += 1
                t.update(1)

        self.stdout.write(
            self.style.SUCCESS("Done. %d errors total." % errors)
        )
