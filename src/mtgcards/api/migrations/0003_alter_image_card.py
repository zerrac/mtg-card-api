# Generated by Django 3.2.16 on 2022-11-07 16:30

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0002_auto_20221107_1414'),
    ]

    operations = [
        migrations.AlterField(
            model_name='image',
            name='card',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, to='api.card'),
        ),
    ]