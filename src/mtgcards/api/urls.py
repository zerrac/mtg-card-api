from django.urls import include, path
from rest_framework import routers
from mtgcards.api import views

router = routers.DefaultRouter()
router.register(r"cards", views.CardViewSet)

urlpatterns =   [
    path('', views.cHomePageView.as_view()),
    path("cards/", views.CardApiView.as_view()),
    path("api/", include(router.urls)),
]
