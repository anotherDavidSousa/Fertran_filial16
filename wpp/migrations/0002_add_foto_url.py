from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('wpp', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='contato',
            name='foto_url',
            field=models.URLField(blank=True, max_length=500, verbose_name='Foto URL'),
        ),
        migrations.AddField(
            model_name='grupoconfig',
            name='foto_url',
            field=models.URLField(blank=True, max_length=500, verbose_name='Foto URL'),
        ),
    ]
