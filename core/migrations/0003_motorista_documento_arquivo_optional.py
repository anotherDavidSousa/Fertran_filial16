# Migration: MotoristaDocumento.arquivo opcional (blank=True, null=True)
# Evita erro 500 ao salvar novo motorista no admin quando o inline de documentos está vazio.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0002_remove_documentotransporte'),
    ]

    operations = [
        migrations.AlterField(
            model_name='motoristadocumento',
            name='arquivo',
            field=models.FileField(blank=True, null=True, upload_to='motoristas/documentos_extras/'),
        ),
    ]
