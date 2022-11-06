# Create your views here.
from mtgcards.api.models import Card
from rest_framework.response import Response
from rest_framework import viewsets
from rest_framework import authentication, permissions
from urllib.request import urlopen
from django.core.files import File
from mtgcards.api.serializers import CardSerializer
from rest_framework.views import APIView
import requests

import os
import mtgcards.api.utils.scryfall as scryfall

import mtgcards.api.utils.images as images


def evaluate_card_score(card: Card, preferred_lang="fr"):
    score = 0
    if card.lang == preferred_lang:
        score += 200
    elif card.lang == "en":
        score += 100

    if card.collector_number.isnumeric():
        score += 80

    if card.type_line.lower().startswith("basic land") and card.full_art:
        score += 50

    if card.frame == "2015":
        score += 40

    if card.edition != "sld":
        score += 10

    if card.image_status == "highres_scan":
        score += 2
    elif card.image_status == "lowres":
        score += 1

    return score


def download(card: Card):
    re = requests.get(card.png_url, stream=True)
    re.raise_for_status()
    re.raw.decode_content = True
    card.image_png = File(re.raw, name=card.name + ".png")
    card.save()
    card.png_bluriness = images.measure_blurriness(card.image_png.path)
    card.save()


class CardViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows cards to be viewed or edited.
    """

    queryset = Card.objects.all().order_by("name")
    serializer_class = CardSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]


class CardApiView(APIView):
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]

    def get(self, request, format=None):

        if "lang" in request.GET:
            preferred_lang = request.GET["lang"]
        else:
            preferred_lang = "en"

        if "name" in request.GET:
            card = request.GET["name"]
        else:
            return Response({"error": "missing name parameter"})

        prints = Card.objects.filter(
            name=request.GET["name"], lang=preferred_lang
        ).exclude(image_status="placeholder")
        if len(prints) == 0:
            prints = Card.objects.filter(name=card).exclude(image_status="placeholder")
        if len(prints) == 0:
            return Response({"Card named %s not found in database" % card})

        selected_print = self.select_best_candidate(prints, preferred_lang)

        if not selected_print.image_png:
            download(selected_print)

        if selected_print.png_bluriness < 200 and preferred_lang != "en":
            selected_print = self.select_best_candidate(prints, preferred_lang)

            if not selected_print.image_png:
                download(selected_print)

        if "debug" in request.GET:
            response = Response(
                CardSerializer(selected_print, context={"request": request}).data
            )
        else:
            response = Response(status=302)
            response["location"] = request.build_absolute_uri(
                selected_print.image_png.url
            )
        return response
        # dest = os.path.join(MEDIA_ROOT, "images", selected_print["name"] + ".png")
        # scryfall.download(scryfall.get_face_url(selected_print), dest)

        # if blur_level < 200 and lang != "en":
        #     print("pouet")
        #     selected_print = self.select_best_candidate(card, "en")

        # response = Response(status=302)
        # response["location"] = scryfall.get_face_url(selected_print)
        # return response

    def select_best_candidate(self, prints, preferred_lang="fr"):

        best_score = 0
        best_content_length = 0
        for print in prints:
            if print.image_status == "placeholder" and len(prints) > 1:
                continue

            print_score = evaluate_card_score(print, preferred_lang)
            if print_score > best_score:
                selected_print = print
                best_score = print_score

                selected_print_content_length = selected_print.image_getsize()
        return selected_print
