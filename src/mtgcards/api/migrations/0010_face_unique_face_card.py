# Generated by Django 4.1.3 on 2022-11-10 17:34

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0009_card_unique_scryfall_id'),
    ]

    operations = [
        migrations.AddConstraint(
            model_name='face',
            constraint=models.UniqueConstraint(fields=('name', 'card'), name='unique_face_card'),
        ),
    ]
