# Generated by Django 3.2.16 on 2022-11-03 18:48

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0004_alter_card_type_line'),
    ]

    operations = [
        migrations.AlterField(
            model_name='card',
            name='type_line',
            field=models.CharField(default='', max_length=500),
        ),
    ]
