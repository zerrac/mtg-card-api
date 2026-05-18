# Create your views here.
from django_filters import rest_framework as filters
from django.db.models import Q, Count
from django.views.generic import TemplateView
from mtgcards.api.utils import scryfall
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import viewsets
from rest_framework import authentication, permissions

from .models import Card, Image, Face
from urllib.request import urlopen
from .serializers import CardSerializer
from . import BLURINESS_HIGH_TRESHOLD, BLURINESS_LOW_TRESHOLD
import requests

import os


from rest_framework.renderers import BaseRenderer, BrowsableAPIRenderer, JSONRenderer
from rest_framework.response import Response
from django.http import FileResponse
class ImageRenderer(BaseRenderer):
    media_type = "image/*"
    format = "image"
    render_style = "binary"

    def render(self, data, accepted_media_type=None, renderer_context=None):
        # data must be raw image bytes
        return data
    

class HomePageView(TemplateView):
    template_name = "home.html"


class CardFilter(filters.FilterSet):
    face_number = filters.NumberFilter(
        label="nombre de faces", method="face_number_filter"
    )
    has_back = filters.BooleanFilter(label="A un dos", method="has_back_filter")

    class Meta:
        model = Card
        fields = "__all__"

    def face_number_filter(self, queryset, name, value):
        queryset = Card.objects.annotate(num_faces=Count("faces")).filter(
            num_faces=value
        )
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

    @staticmethod
    def _client_wants_image_only(request):
        """Returns True if Accept header restricts exclusively to image/* types."""
        accept = request.META.get('HTTP_ACCEPT', '*/*')
        parts = [p.strip().split(';')[0].strip() for p in accept.split(',')]
        non_wildcard = [p for p in parts if p and p != '*/*']
        return bool(non_wildcard) and all(p.startswith('image/') for p in non_wildcard)

    def get(self, request, format=None):
        preferred_lang = request.GET.get("preferred_lang", "en")
        image_format = request.GET.get("image_format", "png")
        face_name = request.GET.get("face_name")
        oracle_id = request.GET.get("oracle_id")
        scryfall_id = request.GET.get("scryfall_id")
        preferred_set = request.GET.get("preferred_set")
        preferred_number = request.GET.get("preferred_number")

        if not oracle_id and not face_name and not scryfall_id:
            return Response({"error": "You must specify 'face_name', 'oracle_id' or 'scryfall_id'"}, status=400)

        faces = (
            Face.objects.filter()
            .exclude(card__image_status__in=["placeholder", "missing"])
            .order_by("card")
        )

        if oracle_id:
            faces = faces.filter(card__oracle_id=oracle_id)
        if scryfall_id:
            faces = faces.filter(card__scryfall_id=scryfall_id)
        if face_name:
            faces = faces.filter(name__iexact=face_name)

        if not faces.exists():
            return Response(
                {"error": "Face named %s with given filters not found in database" % face_name},
                status=404,
            )

        selected_face, selected_image = self._select_with_download(
            faces, preferred_lang, image_format, preferred_number, preferred_set
        )

        if selected_image.bluriness < BLURINESS_LOW_TRESHOLD and preferred_number:
            selected_face, selected_image = self._select_with_download(
                faces, preferred_lang, image_format, None, preferred_set
            )

        if selected_image.bluriness < BLURINESS_LOW_TRESHOLD and preferred_set:
            selected_face, selected_image = self._select_with_download(
                faces, preferred_lang, image_format, None, None
            )

        if selected_image.bluriness < BLURINESS_LOW_TRESHOLD and preferred_lang != "en":
            selected_face, selected_image = self._select_with_download(
                faces, "en", image_format, None, None
            )

        if "debug" in request.GET and not self._client_wants_image_only(request):
            return Response(
                CardSerializer(selected_face.card, context={"request": request}).data
            )

        content_type = "image/jpeg" if image_format == "jpg" else "image/png"
        return FileResponse(selected_image.image.open('rb'), content_type=content_type)

    def _select_with_download(self, faces, preferred_lang, extension, preferred_number, preferred_set):
        face, image = self.select_best_candidate(
            faces,
            preferred_lang=preferred_lang,
            extension=extension,
            preferred_number=preferred_number,
            preferred_set=preferred_set,
        )
        if not image.image:
            image.download()
        return face, image

    def select_best_candidate(self, faces, preferred_lang="fr", extension="jpg", preferred_number=None, preferred_set=None):
        best_score = -1
        for face in faces:
            face_image = face.images.filter(extension=extension).first()

            if not face_image:
                continue
            card_score = face.card.evaluate_score(
                preferred_lang, preferred_number=preferred_number, preferred_set=preferred_set
            )
            if card_score > best_score:
                selected_face = face
                selected_image = face_image
                best_score = card_score
            elif card_score == best_score:
                if not face_image.image:
                    face_image.download()
                if not selected_image.image:
                    selected_image.download()
                if face_image.bluriness > selected_image.bluriness:
                    selected_face = face
                    selected_image = face_image
                    best_score = card_score
            if (
                selected_face.card.lang == preferred_lang
                and selected_image.bluriness > BLURINESS_HIGH_TRESHOLD
            ):
                # Found a high-quality card in the preferred language — no need to keep looking
                break
        return selected_face, selected_image
