# Generated manually - removendo DocumentoTransporte (não usado no Pesseus; processamento de PDF é próprio do projeto)

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0001_initial'),
    ]

    operations = [
        migrations.DeleteModel(name='DocumentoTransporte'),
    ]
