from django.db import migrations, models


def populate_blur_cache(apps, schema_editor):
    Image = apps.get_model('api', 'Image')
    BlurCache = apps.get_model('api', 'BlurCache')
    entries = []
    for img in Image.objects.filter(bluriness__gt=0).select_related('face__card'):
        entries.append(BlurCache(
            scryfall_id=img.face.card.scryfall_id,
            face_index=img.face.face_index,
            extension=img.extension,
            bluriness=img.bluriness,
            image_key=img.image.name if img.image else '',
        ))
    if entries:
        BlurCache.objects.bulk_create(entries, batch_size=1000, ignore_conflicts=True)


class Migration(migrations.Migration):

    dependencies = [
        ('api', '0014_face_index'),
    ]

    operations = [
        migrations.CreateModel(
            name='BlurCache',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('scryfall_id', models.CharField(max_length=100)),
                ('face_index', models.IntegerField(default=0)),
                ('extension', models.CharField(max_length=10)),
                ('bluriness', models.FloatField(default=0.0)),
                ('image_key', models.CharField(default='', max_length=500)),
            ],
        ),
        migrations.AddConstraint(
            model_name='blurcache',
            constraint=models.UniqueConstraint(
                fields=('scryfall_id', 'face_index', 'extension'),
                name='unique_blur_cache',
            ),
        ),
        migrations.RunPython(populate_blur_cache, migrations.RunPython.noop),
    ]
