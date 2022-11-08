# Create your views here.
from django_filters import rest_framework as filters
from django.db.models import Q, Count
from django.views.generic import TemplateView
from mtgcards.api.models import Card, Image, Face
from rest_framework.response import Response
from rest_framework import viewsets
from rest_framework import authentication, permissions
from urllib.request import urlopen
from mtgcards.api.serializers import CardSerializer
from rest_framework.views import APIView
import requests

import os

class HomePageView(TemplateView):
    template_name = "home.html"

class CardFilter(filters.FilterSet):
    face_number = filters.NumberFilter(label="nombre de faces", method="face_number_filter")
    has_back = filters.BooleanFilter(label="A un dos", method="has_back_filter")

    class Meta:
        model = Card
        fields = "__all__"

    def face_number_filter(self, queryset, name, value):
        queryset = Card.objects.annotate(num_faces=Count('faces')).filter(num_faces=value)
        return queryset

    def has_back_filter(self, queryset, name, value):
        if value:
            queryset = Card.objects.filter(faces__side="back")
        else:
            queryset = Card.objects.exclude(faces__side="back")
        return queryset
        


class CardViewSet(viewsets.ModelViewSet):
    """
    API endpoint that allows cards to be viewed or edited.
    """

    queryset = Card.objects.all().order_by("name")
    serializer_class = CardSerializer
    permission_classes = [permissions.IsAuthenticatedOrReadOnly]
    filter_backends = (filters.DjangoFilterBackend,)
    filterset_class = CardFilter

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

        if "format" in request.GET:
            image_format = request.GET["format"]
        else:
            image_format = "jpg"

        prints = Card.objects.filter(
            faces__name=request.GET["name"]
        ).exclude(image_status__in = ["placeholder", "missing"])

        if len(prints) == 0:
            return Response({"Card named %s not found in database" % card})

        localized_prints = prints.filter(lang=preferred_lang)
        if len(localized_prints) == 0:
            selected_print = self.select_best_candidate(prints, preferred_lang)
        else:
            selected_print = self.select_best_candidate(localized_prints, preferred_lang)

        face = Face.objects.get(card=selected_print, name=request.GET["name"])
        image = Image.objects.get(face=face, extension=image_format)


        if image.bluriness < 200 and preferred_lang != "en":
            selected_print = self.select_best_candidate(prints, preferred_lang)
            face = Face.objects.get(card=selected_print, name=request.GET["name"])
            image = Image.objects.get(face=face, extension=image_format)
            if not image.image:
                image.download()

        if "debug" in request.GET:
            response = Response(
                CardSerializer(selected_print, context={"request": request}).data
            )
        else:
            response = Response(status=302)
            response["location"] = request.build_absolute_uri(image.image.url)
        return response

    def select_best_candidate(self, prints, preferred_lang="fr", extension="jpg"):

        best_score = 0
        best_content_length = 0
        for print in prints:
            if print.image_status == "placeholder" and len(prints) > 1:
                continue

            if not print.faces.filter(side="front")[0].images.get(extension=extension).image:
                print.faces.filter(side="front")[0].images.get(extension=extension).download()

            print_score = print.evaluate_score(preferred_lang)
            if print_score > best_score:
                selected_print = print
                selected_face = Face.objects.filter(card=selected_print, side="front")[0]
                selected_image = Image.objects.get(face=selected_face, extension=extension)
                best_score = print_score
            elif print_score == best_score:
                if print.faces.filter(side="front")[0].images.get(extension=extension).bluriness > selected_print.faces.filter(side="front")[0].images.get(extension=extension).bluriness:
                    selected_print = print
                
                
        return selected_print
