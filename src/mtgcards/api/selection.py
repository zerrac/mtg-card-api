from django.db.models import Case, When, IntegerField, Value, Prefetch

from .models import Image
from . import BLURINESS_HIGH_TRESHOLD, DISLIKED_SETS


def select_best_candidate(faces, preferred_lang="fr", extension="jpg", preferred_number=None, preferred_set=None):
    best_card_score = -1
    best_bluriness = -1
    selected_face = None
    selected_image = None
    # Order: preferred-lang highres first, then preferred-lang non-2003, then preferred-lang 2003,
    # then English highres, then English other, then everything else.
    # Once a preferred-lang card is seen (score=200), all English/other cards score ≤100 and are
    # unconditionally skipped, so this ordering eliminates all non-preferred-lang downloads.
    faces = faces.annotate(
        _prio=Case(
            When(card__lang=preferred_lang, card__image_status='highres_scan', then=Value(0)),
            When(card__lang=preferred_lang, card__frame='2003', then=Value(2)),
            When(card__lang=preferred_lang, then=Value(1)),
            When(card__lang='en', card__image_status='highres_scan', then=Value(3)),
            When(card__lang='en', then=Value(4)),
            default=Value(5),
            output_field=IntegerField()
        ),
        _set_prio=Case(
            When(card__edition__in=DISLIKED_SETS, then=Value(1)),
            default=Value(0),
            output_field=IntegerField()
        )
    ).order_by('_set_prio', '_prio', 'card')
    faces = faces.prefetch_related(
        Prefetch("images", queryset=Image.objects.filter(extension=extension), to_attr="prefetched_images")
    )
    for face in faces:
        face_image = face.prefetched_images[0] if face.prefetched_images else None

        if not face_image:
            continue
        card_score = face.card.evaluate_score(
            preferred_lang, preferred_number=preferred_number, preferred_set=preferred_set
        )
        if card_score < best_card_score:
            continue
        if face_image.bluriness == 0:
            face_image.download(store=False)
        if card_score > best_card_score or face_image.bluriness > best_bluriness:
            selected_face = face
            selected_image = face_image
            best_card_score = card_score
            best_bluriness = face_image.bluriness
            if (face.card.lang == preferred_lang
                    and best_bluriness >= BLURINESS_HIGH_TRESHOLD
                    and not preferred_set
                    and not preferred_number):
                break
    return selected_face, selected_image
