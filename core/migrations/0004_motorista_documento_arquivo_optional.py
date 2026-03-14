# Migration: MotoristaDocumento.arquivo opcional (blank=True, null=True)
# Evita erro 500 ao salvar novo motorista no admin quando o inline de documentos está vazio.
# Depende da 0003 existente (carreta_emissao_laudo_cavalo_emissao_laudo_and_more) para evitar conflito.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0003_carreta_emissao_laudo_cavalo_emissao_laudo_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='motoristadocumento',
            name='arquivo',
            field=models.FileField(blank=True, null=True, upload_to='motoristas/documentos_extras/'),
        ),
    ]
