from django.db import models
from django.core.files import File
import requests

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
    full_art = models.BooleanField(default=False)
    
    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["name", "edition", "collector_number", "lang"], name='unique_card_print'),
        ]
        
    def evaluate_score(self, preferred_lang="fr"):
        score = 0
        if self.lang == preferred_lang:
            score += 200
        elif self.lang == "en":
            score += 100

        # if self.collector_number.isnumeric():
        #     score += 80

        # if self.faces.filter(side="front")[0].type_line.lower().startswith("basic land") and self.full_art:
        #     score += 50

        if self.frame == "2015":
            score += 100

        # if self.edition != "sld":
        #     score += 10

        # if self.image_status == "highres_scan":
        #     score += 2
        # elif self.image_status == "lowres":
        #     score += 1

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
    type_line = models.CharField(max_length=500, default="")
    card = models.ForeignKey(Card, on_delete=models.CASCADE, related_name='faces', null=True)
    oracle_text = models.CharField(max_length=10000, default="")

class Image(models.Model):
    image = models.ImageField(upload_to="cards_images", blank=True, null=True)
    extension = models.CharField(max_length=10, default="")
    url = models.URLField(default="")
    bluriness = models.FloatField(default=0.0)
    size = models.IntegerField(default=0)
    face = models.ForeignKey(Face, on_delete=models.CASCADE, related_name='images', null=True)
    
    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['face', 'extension'], name='unique_face_extension'),
        ]

    def getsize(self):
        if self.size == 0:
            self.size == scryfall.image_getsize(self.url)
            self.save()
        return self.size

    def download(self):
        re = requests.get(self.url, stream=True)
        re.raise_for_status()
        re.raw.decode_content = True
        self.image = File(re.raw, name=self.face.name + "." + self.extension)
        self.save()
        self.bluriness = images.measure_blurriness(self.image.path)
        self.save()
