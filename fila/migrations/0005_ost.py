# Generated manually - Model OST (Ordem de Serviço de Transporte)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('fila', '0004_add_manifestado_por_em'),
    ]

    operations = [
        migrations.CreateModel(
            name='OST',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('filial', models.CharField(blank=True, db_index=True, max_length=20, verbose_name='Filial')),
                ('serie', models.CharField(blank=True, db_index=True, max_length=20, verbose_name='Série')),
                ('documento', models.CharField(blank=True, db_index=True, max_length=50, verbose_name='Documento')),
                ('data_manifesto', models.DateField(blank=True, null=True, verbose_name='Data manifesto')),
                ('hora_manifesto', models.TimeField(blank=True, null=True, verbose_name='Hora manifesto')),
                ('remetente', models.CharField(blank=True, max_length=300, verbose_name='Remetente')),
                ('destinatario', models.CharField(blank=True, max_length=300, verbose_name='Destinatário')),
                ('motorista', models.CharField(blank=True, max_length=200, verbose_name='Motorista')),
                ('placa_cavalo', models.CharField(blank=True, max_length=10, verbose_name='Placa cavalo')),
                ('placa_carreta', models.CharField(blank=True, max_length=10, verbose_name='Placa carreta')),
                ('total_frete', models.CharField(blank=True, max_length=50, verbose_name='Total frete')),
                ('pedagio', models.CharField(blank=True, max_length=50, verbose_name='Pedágio')),
                ('valor_tarifa_empresa', models.CharField(blank=True, max_length=50, verbose_name='Valor tarifa empresa')),
                ('produto', models.CharField(blank=True, max_length=500, verbose_name='Produto')),
                ('peso', models.CharField(blank=True, max_length=50, verbose_name='Peso')),
                ('nota_fiscal', models.JSONField(blank=True, default=list, help_text='Lista de NFs ou string única', verbose_name='Nota fiscal')),
                ('data_nf', models.CharField(blank=True, help_text='Datas separadas por " + "', max_length=500, verbose_name='Data NF')),
                ('chave_acesso', models.CharField(blank=True, db_index=True, max_length=50, verbose_name='Chave de acesso NF')),
                ('criado_em', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'verbose_name': 'OST',
                'verbose_name_plural': 'OSTs',
                'ordering': ['-criado_em'],
            },
        ),
    ]
