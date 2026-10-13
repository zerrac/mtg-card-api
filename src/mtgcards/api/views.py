# Create your views here.
from django_filters import rest_framework as filters
from django.db.models import Q, Count, Prefetch
from django.views.generic import TemplateView
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import viewsets
from rest_framework import authentication, permissions
from drf_spectacular.utils import extend_schema, OpenApiParameter, OpenApiResponse
from drf_spectacular.types import OpenApiTypes

from .models import Card, Image, Face
from urllib.request import urlopen
from .serializers import CardSerializer
from . import BLURINESS_LOW_TRESHOLD
from .selection import select_best_candidate, sorted_candidates
import requests

import os


from rest_framework.renderers import BaseRenderer, BrowsableAPIRenderer, JSONRenderer
from rest_framework.response import Response
from django.conf import settings
from django.http import FileResponse, HttpResponseRedirect


class ImageRenderer(BaseRenderer):
    media_type = "image/*"
    format = "image"
    render_style = "binary"

    def render(self, data, accepted_media_type=None, renderer_context=None):
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
            "penalties (tle/fca/prm/mar −100, sld −10). Image sharpness (Laplacian variance) "
            "adds up to 60 bonus points. "
            "On blurry results the selection falls back: preferred_number → "
            "preferred_set → any set → English."
        ),
        parameters=[
            OpenApiParameter("oracle_id", OpenApiTypes.UUID, description="Scryfall oracle ID (mutually exclusive with face_name/scryfall_id)"),
            OpenApiParameter("face_name", OpenApiTypes.STR, description="Card face name, case-insensitive (mutually exclusive with oracle_id/scryfall_id)"),
            OpenApiParameter("scryfall_id", OpenApiTypes.UUID, description="Scryfall card ID (mutually exclusive with oracle_id/face_name)"),
            OpenApiParameter("preferred_lang", OpenApiTypes.STR, default="en", description="ISO 639-1 language code for preferred print (e.g. fr, de, ja)."),
            OpenApiParameter("image_format", OpenApiTypes.STR, enum=["png", "jpg"], default="png", description="Image format to return"),
            OpenApiParameter("side", OpenApiTypes.STR, enum=["front", "back"], default="front", description="Card face side"),
            OpenApiParameter("preferred_set", OpenApiTypes.STR, description="Preferred set code (e.g. lea, m21). Overrides language filter."),
            OpenApiParameter("preferred_number", OpenApiTypes.STR, description="Preferred collector number within the set. Overrides language filter."),
            OpenApiParameter("strict_set", OpenApiTypes.BOOL, required=False, description="Restrict results to preferred_set only (no fallback). Requires preferred_set."),
            OpenApiParameter("strict_number", OpenApiTypes.BOOL, required=False, description="Restrict results to preferred_number only (no fallback). Requires preferred_number."),
            OpenApiParameter("min_bluriness", OpenApiTypes.FLOAT, required=False, description=f"Minimum bluriness threshold for fallback logic. Defaults to {BLURINESS_LOW_TRESHOLD}."),
            OpenApiParameter("debug", OpenApiTypes.BOOL, required=False, description="Return all candidates as JSON with scores instead of the image binary."),
        ],
        responses={
            200: OpenApiResponse(description="Raw image binary (image/png or image/jpeg), or candidates JSON when ?debug is set"),
            400: OpenApiResponse(description="Missing or invalid query parameters"),
            404: OpenApiResponse(description="No matching card face found"),
        },
    )
    def get(self, request, format=None):
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
            preferred_set = request.GET.get("strict_set") or None
        if strict_set and not preferred_set:
            return Response({"error": "'strict_set' requires 'preferred_set'"}, status=400)
        if strict_number and not preferred_number:
            preferred_number = request.GET.get("strict_number") or None
        if strict_number and not preferred_number:
            return Response({"error": "'strict_number' requires 'preferred_number'"}, status=400)

        if not oracle_id and not face_name and not scryfall_id:
            return Response({"error": "You must specify 'face_name', 'oracle_id' or 'scryfall_id'"}, status=400)

        if side not in ("front", "back"):
            return Response({"error": "'side' must be 'front' or 'back'"}, status=400)

        faces = (
            Face.objects.filter(side=side)
            .exclude(card__image_status__in=["placeholder", "missing"])
            .select_related("card")
            .prefetch_related(Prefetch('images', queryset=Image.objects.filter(extension=image_format)))
        )

        if oracle_id:
            faces = faces.filter(card__oracle_id=oracle_id)
        if scryfall_id:
            faces = faces.filter(card__scryfall_id=scryfall_id)
        if face_name:
            faces = faces.filter(name__iexact=face_name)
        if strict_set:
            faces = faces.filter(card__edition__iexact=preferred_set)
        if strict_number:
            faces = faces.filter(card__collector_number__iexact=preferred_number)

        candidates = []
        for face in faces:
            imgs = list(face.images.all())
            if imgs:
                candidates.append((face, imgs[0]))

        if not candidates:
            return Response({"error": "No card or image found for given filters"}, status=404)

        levels = [(preferred_lang, preferred_number, preferred_set)]
        if preferred_number and not strict_number:
            levels.append((preferred_lang, None, preferred_set))
        if preferred_set and not strict_set:
            levels.append((preferred_lang, None, None))
        if preferred_lang != "en":
            levels.append(("en", None, None))

        selected_face, selected_image = None, None
        for lang, num, sset in levels:
            f, i = self._find_non_blurry(candidates, min_bluriness, lang, num, sset)
            if f is not None:
                selected_face, selected_image = f, i
                break

        if selected_face is None:
            selected_face, selected_image = self._select_from_candidates(
                candidates, preferred_lang, preferred_number, preferred_set
            )

        if "debug" in request.GET:
            return Response(self._build_debug_response(
                candidates, preferred_lang, preferred_number, preferred_set,
                selected_face,
            ))

        if settings.USE_SCRYFALL_REDIRECT:
            url = selected_image.url
        else:
            if not selected_image.image:
                selected_image.download()
            url = selected_image.image.url
        return HttpResponseRedirect(url)

    def _build_debug_response(self, candidates, preferred_lang, preferred_number, preferred_set, selected_face):
        rows = []
        for face, image in candidates:
            card_score = face.card.evaluate_score(
                preferred_lang, preferred_number=preferred_number, preferred_set=preferred_set
            )
            rows.append({
                "selected": face.pk == selected_face.pk,
                "name": face.card.name,
                "edition": face.card.edition,
                "lang": face.card.lang,
                "collector_number": face.card.collector_number,
                "card_score": card_score,
                "bluriness": round(image.bluriness, 2),
            })
        rows.sort(key=lambda c: (c["card_score"], c["bluriness"]), reverse=True)
        return {"preferred_lang": preferred_lang, "candidates": rows}

    def _find_non_blurry(self, candidates, min_bluriness, preferred_lang, preferred_number, preferred_set):
        """Walk candidates in score order; return first (face, image) with bluriness >= min_bluriness."""
        for face, image in sorted_candidates(candidates, preferred_lang, preferred_number, preferred_set):
            if image.bluriness == 0:
                image.download(store=False)
            if image.bluriness >= min_bluriness:
                return face, image
        return None, None

    def _select_from_candidates(self, candidates, preferred_lang, preferred_number, preferred_set):
        """Last-resort fallback: return best-scored candidate regardless of bluriness."""
        face, image = select_best_candidate(
            candidates,
            preferred_lang=preferred_lang,
            preferred_number=preferred_number,
            preferred_set=preferred_set,
        )
        if image is not None and image.bluriness == 0:
            image.download(store=False)
        return face, image
