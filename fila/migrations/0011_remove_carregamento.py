from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('fila', '0010_api_key'),
    ]

    operations = [
        migrations.DeleteModel(
            name='Carregamento',
        ),
    ]
