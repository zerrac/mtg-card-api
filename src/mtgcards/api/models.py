from django.db import models
from django.core.files import File
from django.db.models.functions import Upper
from io import BytesIO

from .utils import images
from .utils import scryfall

# Create your models here.
class Card(models.Model):
    name = models.CharField(max_length=500)
    collector_number = models.CharField(max_length=10)
    edition = models.CharField(max_length=10)

    scryfall_id = models.CharField(max_length=100, default="")
    oracle_id = models.CharField(max_length=100, default="")
    scryfall_api_url = models.URLField(default="")

    # Image info
    image_status = models.CharField(max_length=100, default="")
    frame = models.CharField(max_length=10, default="")
    lang = models.CharField(max_length=10, default="")
    layout = models.CharField(max_length=50, default="")
    full_art = models.BooleanField(default=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["name", "edition", "collector_number", "lang"],
                name="unique_card_print",
            ),
            models.UniqueConstraint(fields=["scryfall_id"], name="unique_scryfall_id"),
        ]

    def evaluate_score(self, preferred_lang="fr", preferred_number=None, preferred_set=None):
        score = 0
        if self.lang == preferred_lang:
            score += 200
        elif self.lang == "en":
            score += 100

        if self.collector_number.isnumeric():
            score += 50

        # if self.faces.filter(side="front")[0].type_line.lower().startswith("basic land") and self.full_art:
        #     score += 50

        if self.frame.isdigit() and int(self.frame) >= 2003:
            score += 50

        if self.edition != "sld":
            score += 10

        # Nobody likes tle
        if self.edition in ['tle', 'fca', 'prm', 'mar'] and not preferred_set:
            score -= 100

        # if self.image_status == "highres_scan":
        #     score += 2
        # elif self.image_status == "lowres":
        #     score += 1

        if preferred_set and self.edition.lower() == preferred_set.lower():
            score += 1500

        if preferred_number and self.collector_number.lower() == preferred_number.lower():
            score += 3000

        return score

    def __str__(self):
        return self.name

SIDES_CHOICES = [
    ("front", "front"),
    ("back", "back"),
]
class Face(models.Model):
    name = models.CharField(max_length=500, default="")
    side = models.CharField(max_length=5, choices=SIDES_CHOICES, default="front")
    face_index = models.IntegerField(default=0)
    type_line = models.CharField(max_length=500, default="")
    card = models.ForeignKey(
        Card, on_delete=models.CASCADE, related_name="faces", null=True
    )
    oracle_text = models.CharField(max_length=10000, default="")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["card", "face_index"], name="unique_face_card_index"),
        ]
        indexes = [
            models.Index(Upper('name'), name='face_name_upper_idx'),
        ]

class BlurCache(models.Model):
    """Persists locally computed bluriness and image file references across re-imports."""
    scryfall_id = models.CharField(max_length=100)
    face_index = models.IntegerField(default=0)
    extension = models.CharField(max_length=10)
    bluriness = models.FloatField(default=0.0)
    image_key = models.CharField(max_length=500, default="")

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["scryfall_id", "face_index", "extension"],
                name="unique_blur_cache",
            ),
        ]


class Image(models.Model):
    image = models.ImageField(upload_to="cards_images", blank=True, null=True)
    extension = models.CharField(max_length=10, default="")
    url = models.URLField(default="")
    bluriness = models.FloatField(default=0.0)
    size = models.IntegerField(default=0)
    face = models.ForeignKey(
        Face, on_delete=models.CASCADE, related_name="images", null=True
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["face", "extension"], name="unique_face_extension"
            ),
        ]

    def getsize(self):
        if self.size == 0:
            self.size = scryfall.image_getsize(self.url)
            self.save()
        return self.size

    def download(self):
        response = scryfall.http.get(self.url, timeout=30)
        response.raise_for_status()
        self.bluriness = images.measure_blurriness(response.content)
        self.image = File(BytesIO(response.content), name=self.face.name + "." + self.extension)
        self.save()
        BlurCache.objects.update_or_create(
            scryfall_id=self.face.card.scryfall_id,
            face_index=self.face.face_index,
            extension=self.extension,
            defaults={"bluriness": self.bluriness, "image_key": self.image.name},
        )
