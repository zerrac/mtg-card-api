from django.db import models
from django.core.files import File
import requests

import mtgcards.api.utils.images as images
import mtgcards.api.utils.scryfall as scryfall

# Create your models here.
class Card(models.Model):
    name = models.CharField(max_length=500)
    collector_number = models.CharField(max_length=10)
    edition = models.CharField(max_length=10)

    # Image info
    image_status = models.CharField(max_length=100, default="")
    frame = models.CharField(max_length=10, default="")
    type_line = models.CharField(max_length=500, default="")
    lang = models.CharField(max_length=10, default="")
    full_art = models.BooleanField(default=False)

    def evaluate_score(self, preferred_lang="fr"):
        score = 0
        if self.lang == preferred_lang:
            score += 200
        elif self.lang == "en":
            score += 100

        if self.collector_number.isnumeric():
            score += 80

        if self.type_line.lower().startswith("basic land") and self.full_art:
            score += 50

        if self.frame == "2015":
            score += 40

        if self.edition != "sld":
            score += 10

        if self.image_status == "highres_scan":
            score += 2
        elif self.image_status == "lowres":
            score += 1

        return score

    def __str__(self):
        return self.name


class Image(models.Model):
    image = models.ImageField(upload_to="cards_images", blank=True, null=True)
    extension = models.CharField(max_length=10, default="")
    url = models.URLField(default="")
    bluriness = models.FloatField(default=0.0)
    size = models.IntegerField(default=0)
    card = models.ForeignKey(Card, on_delete=models.CASCADE, blank=True, null=True)
    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['card'], condition=models.Q(extension="png"), name='unique_png_card'),
            models.UniqueConstraint(fields=['card'], condition=models.Q(extension="jpg"), name='unique_jpg_card')
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
        self.image = File(re.raw, name=self.card.name + "." + self.extension)
        self.save()
        self.bluriness = images.measure_blurriness(self.image.path)
        self.save()
