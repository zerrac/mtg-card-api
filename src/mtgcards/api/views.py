# Create your views here.
from django_filters import rest_framework as filters
from django.db.models import Q, Count
from django.views.generic import TemplateView
from mtgcards.api.utils import scryfall
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import viewsets
from rest_framework import authentication, permissions
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiResponse
from drf_spectacular.types import OpenApiTypes

from .models import Card, Image, Face
from urllib.request import urlopen
from .serializers import CardSerializer
from . import BLURINESS_HIGH_TRESHOLD, BLURINESS_LOW_TRESHOLD
import requests

import os
import time
import logging

logger = logging.getLogger(__name__)

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
    renderer_classes = [JSONRenderer, BrowsableAPIRenderer, ImageRenderer]

    @extend_schema(
        summary="Get best card image",
        description=(
            "Returns the best available card image for the given card identifier. "
            "Scoring weighs language preference (+200 preferred lang, +100 English), "
            "numeric collector number (+50), frame era ≥ 2003 (+50), with set-specific "
            "penalties (tle −100, sld −10). Ties are broken by image sharpness "
            "(Laplacian variance; higher = sharper). "
            "When `preferred_set` or `preferred_number` is provided the language filter "
            "is skipped. On blurry results the selection falls back: preferred_number → "
            "preferred_set → any set → English."
        ),
        parameters=[
            OpenApiParameter("oracle_id", OpenApiTypes.UUID, description="Scryfall oracle ID (mutually exclusive with face_name/scryfall_id)"),
            OpenApiParameter("face_name", OpenApiTypes.STR, description="Card face name, case-insensitive (mutually exclusive with oracle_id/scryfall_id)"),
            OpenApiParameter("scryfall_id", OpenApiTypes.UUID, description="Scryfall card ID (mutually exclusive with oracle_id/face_name)"),
            OpenApiParameter("preferred_lang", OpenApiTypes.STR, default="en", description="ISO 639-1 language code for preferred print (e.g. fr, de, ja). Skipped when preferred_set or preferred_number is set."),
            OpenApiParameter("image_format", OpenApiTypes.STR, enum=["png", "jpg"], default="png", description="Image format to return"),
            OpenApiParameter("side", OpenApiTypes.STR, enum=["front", "back"], default="front", description="Card face side"),
            OpenApiParameter("preferred_set", OpenApiTypes.STR, description="Preferred set code (e.g. lea, m21). Overrides language filter."),
            OpenApiParameter("preferred_number", OpenApiTypes.STR, description="Preferred collector number within the set. Overrides language filter."),
            OpenApiParameter("strict_set", OpenApiTypes.BOOL, required=False, description="When present, restrict results to preferred_set only (no fallback). Requires preferred_set."),
            OpenApiParameter("strict_number", OpenApiTypes.BOOL, required=False, description="When present, restrict results to preferred_number only (no fallback). Requires preferred_number."),
            OpenApiParameter("min_bluriness", OpenApiTypes.FLOAT, required=False, description=f"Minimum bluriness (Laplacian variance) threshold for fallback logic. Defaults to {BLURINESS_LOW_TRESHOLD}."),
            OpenApiParameter("debug", OpenApiTypes.BOOL, required=False, description="When present, return card JSON instead of the image binary."),
        ],
        responses={
            200: OpenApiResponse(description="Raw image binary (image/png or image/jpeg), or card JSON when ?debug is set"),
            400: OpenApiResponse(description="Missing or invalid query parameters"),
            404: OpenApiResponse(description="No matching card face found"),
        },
    )
    def get(self, request, format=None):
        t_start = time.perf_counter()
        preferred_lang = request.GET.get("preferred_lang", "en")
        image_format = request.GET.get("image_format", "png")
        face_name = request.GET.get("face_name")
        oracle_id = request.GET.get("oracle_id")
        scryfall_id = request.GET.get("scryfall_id")
        preferred_set = request.GET.get("preferred_set")
        preferred_number = request.GET.get("preferred_number")
        side = request.GET.get("side", "front")
        try:
            min_bluriness = float(request.GET.get("min_bluriness", BLURINESS_LOW_TRESHOLD))
        except ValueError:
            return Response({"error": "'min_bluriness' must be a number"}, status=400)
        strict_set = "strict_set" in request.GET
        strict_number = "strict_number" in request.GET

        if strict_set and not preferred_set:
            return Response({"error": "'strict_set' requires 'preferred_set'"}, status=400)
        if strict_number and not preferred_number:
            return Response({"error": "'strict_number' requires 'preferred_number'"}, status=400)

        if not oracle_id and not face_name and not scryfall_id:
            return Response({"error": "You must specify 'face_name', 'oracle_id' or 'scryfall_id'"}, status=400)

        if side not in ("front", "back"):
            return Response({"error": "'side' must be 'front' or 'back'"}, status=400)

        faces = (
            Face.objects.filter(side=side)
            .exclude(card__image_status__in=["placeholder", "missing"])
            .order_by("card")
        )

        if oracle_id:
            faces = faces.filter(card__oracle_id=oracle_id)
        if scryfall_id:
            faces = faces.filter(card__scryfall_id=scryfall_id)
        if face_name:
            faces = faces.filter(name__iexact=face_name)
            # For 'prepare' layout cards only the primary (first) face is standalone;
            # exclude faces where face_name is the secondary name after ' // '.
            faces = faces.exclude(
                card__layout='prepare',
                card__name__iendswith=' // ' + face_name,
            )
        if strict_set:
            faces = faces.filter(card__edition__iexact=preferred_set)
        if strict_number:
            faces = faces.filter(card__collector_number__iexact=preferred_number)

        if not faces.exists():
            return Response(
                {"error": "Face named %s with given filters not found in database" % face_name},
                status=404,
            )

        selected_face, selected_image = self._select_with_download(
            faces, preferred_lang, image_format, preferred_number, preferred_set
        )

        if selected_image.bluriness < min_bluriness and preferred_number and not strict_number:
            selected_face, selected_image = self._select_with_download(
                faces, preferred_lang, image_format, None, preferred_set
            )

        if selected_image.bluriness < min_bluriness and preferred_set and not strict_set:
            selected_face, selected_image = self._select_with_download(
                faces, preferred_lang, image_format, None, None
            )

        if selected_image.bluriness < min_bluriness and preferred_lang != "en":
            selected_face, selected_image = self._select_with_download(
                faces, "en", image_format, None, None
            )

        total_ms = (time.perf_counter() - t_start) * 1000
        logger.info(
            "card_request card=%s total=%.0fms",
            face_name or oracle_id or scryfall_id,
            total_ms,
        )

        if "debug" in request.GET:
            return Response(CardSerializer(selected_face.card, context={"request": request}).data)

        content_type = "image/jpeg" if image_format == "jpg" else "image/png"
        return FileResponse(selected_image.image.open('rb'), content_type=content_type)

    def _select_with_download(self, faces, preferred_lang, extension, preferred_number, preferred_set):
        t0 = time.perf_counter()
        face, image = self.select_best_candidate(
            faces,
            preferred_lang=preferred_lang,
            extension=extension,
            preferred_number=preferred_number,
            preferred_set=preferred_set,
        )
        t1 = time.perf_counter()
        needs_download = not image.image
        if needs_download:
            image.download()
        t2 = time.perf_counter()
        logger.info(
            "select_with_download lang=%s set=%s number=%s select=%.0fms download=%.0fms downloaded=%s",
            preferred_lang, preferred_set, preferred_number,
            (t1 - t0) * 1000, (t2 - t1) * 1000, needs_download,
        )
        return face, image

    def select_best_candidate(self, faces, preferred_lang="fr", extension="jpg", preferred_number=None, preferred_set=None):
        t0 = time.perf_counter()
        best_score = -1
        face_count = 0
        for face in faces:
            face_count += 1
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
        logger.info(
            "select_best_candidate faces=%d time=%.0fms",
            face_count, (time.perf_counter() - t0) * 1000,
        )
        return selected_face, selected_image
