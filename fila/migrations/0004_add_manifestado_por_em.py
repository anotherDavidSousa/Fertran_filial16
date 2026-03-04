# Generated manually for dashboard: manifestados por colaborador

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('fila', '0003_alter_carregamento_options'),
    ]

    operations = [
        migrations.AddField(
            model_name='carregamento',
            name='manifestado_por',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='carregamentos_manifestados',
                to=settings.AUTH_USER_MODEL,
                verbose_name='Manifestado por',
            ),
        ),
        migrations.AddField(
            model_name='carregamento',
            name='manifestado_em',
            field=models.DateTimeField(blank=True, null=True, verbose_name='Manifestado em'),
        ),
    ]
