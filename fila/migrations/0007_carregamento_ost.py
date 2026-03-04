# Generated manually - vínculo Carregamento com OST (match processador → fila)

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('fila', '0006_ost_pdf_storage_key'),
    ]

    operations = [
        migrations.AddField(
            model_name='carregamento',
            name='ost',
            field=models.ForeignKey(
                blank=True,
                help_text='Preenchido quando o item foi manifestado automaticamente pelo match com OST processada.',
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name='carregamentos',
                to='fila.ost',
                verbose_name='OST vinculada',
            ),
        ),
    ]
