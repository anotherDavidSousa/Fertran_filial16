# Generated manually - PDF da OST no MinIO (demembramento por página)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('fila', '0005_ost'),
    ]

    operations = [
        migrations.AddField(
            model_name='ost',
            name='pdf_storage_key',
            field=models.CharField(
                blank=True,
                help_text='Objeto no bucket para download do PDF desta OST.',
                max_length=500,
                verbose_name='Chave do PDF no MinIO',
            ),
        ),
    ]
