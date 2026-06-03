from django.db import migrations, models
from django.db.models.functions import Upper


class Migration(migrations.Migration):

    dependencies = [
        ("api", "0012_card_layout_face_index"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="face",
            index=models.Index(Upper("name"), name="face_name_upper_idx"),
        ),
        migrations.AddIndex(
            model_name="face",
            index=models.Index(fields=["side"], name="face_side_idx"),
        ),
        migrations.AddIndex(
            model_name="card",
            index=models.Index(fields=["oracle_id"], name="card_oracle_id_idx"),
        ),
        migrations.AddIndex(
            model_name="card",
            index=models.Index(fields=["image_status"], name="card_image_status_idx"),
        ),
    ]
