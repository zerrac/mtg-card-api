# Generated by Django 3.2.16 on 2022-11-06 21:13

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0009_image_card'),
    ]

    operations = [
        migrations.AddConstraint(
            model_name='image',
            constraint=models.UniqueConstraint(condition=models.Q(('extension', 'png')), fields=('card',), name='unique_png_card'),
        ),
        migrations.AddConstraint(
            model_name='image',
            constraint=models.UniqueConstraint(condition=models.Q(('extension', 'jpg')), fields=('card',), name='unique_jpg_card'),
        ),
    ]