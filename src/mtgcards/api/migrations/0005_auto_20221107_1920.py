# Generated by Django 3.2.16 on 2022-11-07 19:20

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0004_auto_20221107_1910'),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name='face',
            name='unique_card_side',
        ),
        migrations.RemoveField(
            model_name='face',
            name='side',
        ),
    ]