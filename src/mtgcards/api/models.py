from django.db import models
from django.core.files.base import ContentFile
import urllib.request

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

        if self.frame.isdigit() and int(self.frame) >= 2003:
            score += 50

        if self.edition != "sld":
            score += 10

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
            self.size == scryfall.image_getsize(self.url)
            self.save()
        return self.size

    def download(self, store=True):
        key = f"cards/{self.face.card.scryfall_id}/{self.face.face_index}.{self.extension}"
        storage = self.image.storage

        if store and storage.exists(key):
            data = storage.open(key).read()
            self.image.name = key
        else:
            req = urllib.request.Request(
                self.url,
                data=None,
                headers={
                    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_9_3) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/35.0.1916.47 Safari/537.36"
                },
            )
            data = urllib.request.urlopen(req).read()
            if store:
                key = storage.save(key, ContentFile(data))
                self.image.name = key

        self.bluriness = images.measure_blurriness_from_bytes(data)
        self.save()
