# Generated manually - modelo ApiKey (integração n8n / X-Api-Key)

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('fila', '0009_cte_model'),
    ]

    operations = [
        migrations.CreateModel(
            name='ApiKey',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('token', models.CharField(blank=True, db_index=True, max_length=64, unique=True)),
                ('descricao', models.CharField(blank=True, max_length=200, verbose_name='Descrição')),
                ('ativo', models.BooleanField(default=True, verbose_name='Ativo')),
                ('criado_em', models.DateTimeField(auto_now_add=True, verbose_name='Criado em')),
                ('ultimo_uso', models.DateTimeField(blank=True, null=True, verbose_name='Último uso')),
                (
                    'user',
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name='api_keys',
                        to=settings.AUTH_USER_MODEL,
                        verbose_name='Usuário',
                    ),
                ),
            ],
            options={
                'verbose_name': 'API Key',
                'verbose_name_plural': 'API Keys',
            },
        ),
    ]
