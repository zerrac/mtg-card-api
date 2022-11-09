# Create your views here.
from django_filters import rest_framework as filters
from django.db.models import Q, Count
from django.views.generic import TemplateView
from .models import Card, Image, Face
from rest_framework.response import Response
from rest_framework import viewsets
from rest_framework import authentication, permissions
from urllib.request import urlopen
from .serializers import CardSerializer
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

        if "face_name" in request.GET:
            face_name = request.GET["face_name"]
        else:
            return Response({"error": "face_name parameter is mandatory"}, status=400)

        if "format" in request.GET:
            image_format = request.GET["format"]
        else:
            image_format = "jpg"

        faces = Face.objects.filter(
            name=face_name,
            card__lang__in=[preferred_lang, "en"]
        ).exclude(card__image_status__in = ["placeholder", "missing"]).order_by("card")

        if len(faces) == 0:
            return Response({"Face named %s not found in database" % face_name}, status=404)

        selected_face = self.select_best_candidate(faces, preferred_lang=preferred_lang, extension=image_format)

        image = selected_face.images.get(extension=image_format)
        if not image.image:
            image.download()

        if "debug" in request.GET:
            response = Response(
                CardSerializer(selected_face.card, context={"request": request}).data
            )
        else:
            response = Response(status=302)
            response["location"] = request.build_absolute_uri(image.image.url)
        return response

    def select_best_candidate(self, faces, preferred_lang="fr", extension="jpg"):
        best_score = -1
        for face in faces:
            face_image = face.images.get(extension=extension)

            card_score = face.card.evaluate_score(preferred_lang)
            if card_score > best_score:
                if not face_image.image:
                    face_image.download()
                selected_face = face
                selected_image = face_image
                best_score = card_score
            elif card_score == best_score:
                if not face_image.image:
                    face_image.download()
                if face_image.bluriness > selected_image.bluriness:
                    selected_face = face
                    best_score = card_score
                
        return selected_face
