from django.db import models
import mtgcards.api.lib.scryfall as scryfall

# Create your models here.


class Card(models.Model):
    name = models.CharField(max_length=500)
    collector_number = models.CharField(max_length=10)
    edition = models.CharField(max_length=10)
    image_status = models.CharField(max_length=100, default="")
    image_png = models.ImageField(upload_to="cards_images", blank=True, null=True)
    png_url = models.URLField(default="")
    png_bluriness = models.FloatField(default=0.0)
    image_size = models.IntegerField(default=0)
    frame = models.CharField(max_length=10, default="")
    type_line = models.CharField(max_length=500, default="")
    lang = models.CharField(max_length=10, default="")
    full_art = models.BooleanField(default=False)

    def image_getsize(self):
        if self.image_size == 0:
            self.image_size == scryfall.image_getsize(self.png_url)
            self.save()
        return self.image_size

    def __str__(self):
        return self.name
