from django.urls import include, path
from rest_framework import routers
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView
from mtgcards.api import views

router = routers.DefaultRouter()
router.register(r"cards", views.CardViewSet)

urlpatterns = [
    path("", views.HomePageView.as_view()),
    path("cards/", views.CardApiView.as_view()),
    path("api/", include(router.urls)),
    path("schema/", SpectacularAPIView.as_view(), name="schema"),
    path("docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
]
