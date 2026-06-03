from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0011_remove_face_unique_face_card"),
    ]

    operations = [
        migrations.AddField(
            model_name="card",
            name="layout",
            field=models.CharField(default="", max_length=50),
        ),
        migrations.AddField(
            model_name="face",
            name="face_index",
            field=models.IntegerField(default=0),
        ),
        migrations.AddConstraint(
            model_name="face",
            constraint=models.UniqueConstraint(fields=["card", "face_index"], name="unique_face_card_index"),
        ),
    ]
