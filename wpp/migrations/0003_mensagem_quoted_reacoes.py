from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('wpp', '0002_add_foto_url'),
    ]

    operations = [
        migrations.AddField(
            model_name='mensagem',
            name='quoted_msg_id',
            field=models.CharField(blank=True, max_length=100, verbose_name='ID mensagem citada'),
        ),
        migrations.AddField(
            model_name='mensagem',
            name='quoted_sender_nome',
            field=models.CharField(blank=True, max_length=200, verbose_name='Nome remetente citado'),
        ),
        migrations.AddField(
            model_name='mensagem',
            name='quoted_texto',
            field=models.TextField(blank=True, verbose_name='Texto citado'),
        ),
        migrations.AddField(
            model_name='mensagem',
            name='quoted_tipo',
            field=models.CharField(blank=True, max_length=20, verbose_name='Tipo citado'),
        ),
        migrations.AddField(
            model_name='mensagem',
            name='reacoes',
            field=models.JSONField(blank=True, default=dict, verbose_name='Reações'),
        ),
    ]
