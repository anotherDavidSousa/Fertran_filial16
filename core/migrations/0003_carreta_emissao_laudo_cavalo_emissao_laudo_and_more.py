# Recriada manualmente: estava em produção mas nunca foi commitada no git.
# Adicionou emissao_laudo em Carreta e Cavalo, e criou os 4 models de documentos extras.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0002_remove_documentotransporte'),
    ]

    operations = [
        # ── Campos emissao_laudo ──────────────────────────────────────────────
        migrations.AddField(
            model_name='carreta',
            name='emissao_laudo',
            field=models.DateField(blank=True, null=True, verbose_name='Emissão do laudo'),
        ),
        migrations.AddField(
            model_name='cavalo',
            name='emissao_laudo',
            field=models.DateField(blank=True, null=True, verbose_name='Emissão do laudo'),
        ),

        # ── CavaloDocumento ───────────────────────────────────────────────────
        migrations.CreateModel(
            name='CavaloDocumento',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('arquivo', models.FileField(upload_to='cavalos/documentos_extras/')),
                ('criado_em', models.DateTimeField(auto_now_add=True)),
                ('cavalo', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='documentos_extras',
                    to='core.cavalo',
                )),
            ],
            options={
                'verbose_name': 'Documento do Cavalo',
                'verbose_name_plural': 'Documentos do Cavalo',
            },
        ),

        # ── CarretaDocumento ──────────────────────────────────────────────────
        migrations.CreateModel(
            name='CarretaDocumento',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('arquivo', models.FileField(upload_to='carretas/documentos_extras/')),
                ('criado_em', models.DateTimeField(auto_now_add=True)),
                ('carreta', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='documentos_extras',
                    to='core.carreta',
                )),
            ],
            options={
                'verbose_name': 'Documento da Carreta',
                'verbose_name_plural': 'Documentos da Carreta',
            },
        ),

        # ── ProprietarioDocumento ─────────────────────────────────────────────
        migrations.CreateModel(
            name='ProprietarioDocumento',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('arquivo', models.FileField(upload_to='proprietarios/documentos_extras/')),
                ('criado_em', models.DateTimeField(auto_now_add=True)),
                ('proprietario', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='documentos_extras',
                    to='core.proprietario',
                )),
            ],
            options={
                'verbose_name': 'Documento do Proprietário',
                'verbose_name_plural': 'Documentos do Proprietário',
            },
        ),

        # ── MotoristaDocumento ────────────────────────────────────────────────
        migrations.CreateModel(
            name='MotoristaDocumento',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('arquivo', models.FileField(upload_to='motoristas/documentos_extras/')),
                ('criado_em', models.DateTimeField(auto_now_add=True)),
                ('motorista', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='documentos_extras',
                    to='core.motorista',
                )),
            ],
            options={
                'verbose_name': 'Documento do Motorista',
                'verbose_name_plural': 'Documentos do Motorista',
            },
        ),
    ]
