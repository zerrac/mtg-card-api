from .models import Card, Face, Image
from rest_framework import serializers


class ImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = Image
        exclude = ["face"]


class FaceSerializer(serializers.ModelSerializer):
    images = ImageSerializer(many=True, read_only=True)

    class Meta:
        model = Face
        exclude = ["card"]


class CardSerializer(serializers.HyperlinkedModelSerializer):
    faces = FaceSerializer(many=True, read_only=True)
    # faces = serializers.SlugRelatedField(
    #     many=True,
    #     read_only=True,
    #     slug_field='name'
    #  )
    class Meta:
        model = Card
        fields = "__all__"
        depth = 3
