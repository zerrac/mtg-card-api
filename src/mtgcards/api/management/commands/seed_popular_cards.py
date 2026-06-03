import os
import time

from django.core.management.base import BaseCommand
from django.db.models import Case, When, IntegerField, Value, Prefetch

from ...models import Card, Face, Image
from ... import BLURINESS_HIGH_TRESHOLD, DISLIKED_SETS

FIXTURE_PATH = os.path.join(os.path.dirname(__file__), "../../fixtures/popular_cards.txt")

SIDES = ["front", "back"]


class Command(BaseCommand):
    help = "Pre-seed R2 with the best images for the most popular EDH cards"

    def add_arguments(self, parser):
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
        parser.add_argument(
            "--fixture",
            default=FIXTURE_PATH,
            help="Path to plain-text fixture file with one card name per line",
        )

    def handle(self, *args, **options):
        extension = options["extension"]
        langs = options["langs"]
        fixture_path = options["fixture"]

        with open(fixture_path) as f:
            names = [line.strip() for line in f if line.strip()]

        oracle_ids = list(
            Card.objects.filter(name__in=names)
            .values_list("oracle_id", flat=True)
            .distinct()
        )

        found = len(oracle_ids)
        self.stdout.write(
            "Found %d oracle_ids for %d card names (langs: %s, ext: %s)"
            % (found, len(names), " ".join(langs), extension)
        )
        if found == 0:
            self.stderr.write("No cards found — is the database populated?")
            return

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


def _select_bulk(oracle_ids, lang, side, extension):
    """One DB round-trip per (lang, side): fetch all oracle_ids at once and select the best image for each."""
    faces_qs = (
        Face.objects.filter(
            side=side,
            card__oracle_id__in=oracle_ids,
            card__lang=lang,
        )
        .exclude(card__image_status__in=["placeholder", "missing"])
        .select_related("card")
        .prefetch_related(
            Prefetch(
                "images",
                queryset=Image.objects.filter(extension=extension),
                to_attr="prefetched_images",
            )
        )
        .annotate(
            _prio=Case(
                When(card__image_status="highres_scan", then=Value(0)),
                When(card__frame="2003", then=Value(2)),
                default=Value(1),
                output_field=IntegerField(),
            ),
            _set_prio=Case(
                When(card__edition__in=DISLIKED_SETS, then=Value(1)),
                default=Value(0),
                output_field=IntegerField(),
            ),
        )
        .order_by("card__oracle_id", "_set_prio", "_prio", "card")
    )

    selected = []
    errors = 0
    current_oracle_id = None
    best_score = -1
    best_bluriness = -1
    best_image = None
    done = False

    for face in faces_qs:
        oracle_id = face.card.oracle_id

        if oracle_id != current_oracle_id:
            if best_image is not None and not best_image.image:
                selected.append(best_image)
            current_oracle_id = oracle_id
            best_score = -1
            best_bluriness = -1
            best_image = None
            done = False

        if done:
            continue

        face_image = face.prefetched_images[0] if face.prefetched_images else None
        if not face_image:
            continue

        card_score = face.card.evaluate_score(lang)
        if card_score < best_score:
            continue

        if face_image.bluriness == 0:
            try:
                face_image.download(store=False)
            except Exception as e:
                errors += 1
                continue

        if card_score > best_score or face_image.bluriness > best_bluriness:
            best_image = face_image
            best_score = card_score
            best_bluriness = face_image.bluriness
            if best_bluriness >= BLURINESS_HIGH_TRESHOLD:
                done = True

    if best_image is not None and not best_image.image:
        selected.append(best_image)

    return selected, errors
