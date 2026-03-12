# Generated manually - Model CTe (Conhecimento de Transporte Eletrônico)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('fila', '0008_alter_ost_criado_em'),
    ]

    operations = [
        migrations.CreateModel(
            name='CTe',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('filial', models.CharField(blank=True, db_index=True, max_length=20, verbose_name='Filial')),
                ('serie', models.CharField(blank=True, db_index=True, max_length=20, verbose_name='Série')),
                ('numero_cte', models.CharField(blank=True, db_index=True, max_length=50, verbose_name='Número CT-e')),
                ('data_emissao', models.DateField(blank=True, null=True, verbose_name='Data emissão')),
                ('hora_emissao', models.TimeField(blank=True, null=True, verbose_name='Hora emissão')),
                ('remetente', models.CharField(blank=True, max_length=500, verbose_name='Remetente')),
                ('municipio_remetente', models.CharField(blank=True, max_length=200, verbose_name='Município remetente')),
                ('destinatario', models.CharField(blank=True, max_length=500, verbose_name='Destinatário')),
                ('municipio_destinatario', models.CharField(blank=True, max_length=200, verbose_name='Município destinatário')),
                ('produto_predominante', models.CharField(blank=True, max_length=500, verbose_name='Produto predominante')),
                ('vlr_tarifa', models.CharField(blank=True, max_length=50, verbose_name='Valor tarifa')),
                ('peso_bruto', models.CharField(blank=True, max_length=50, verbose_name='Peso bruto')),
                ('frete_peso', models.CharField(blank=True, max_length=50, verbose_name='Frete peso')),
                ('pedagio', models.CharField(blank=True, max_length=50, verbose_name='Pedágio')),
                ('valor_total', models.CharField(blank=True, max_length=50, verbose_name='Valor total')),
                ('serie_nf', models.CharField(blank=True, help_text='Série do documento NF-e (ex.: 0)', max_length=20, verbose_name='Série NF')),
                ('nota_fiscal', models.CharField(blank=True, db_index=True, help_text='Número da NF-e', max_length=50, verbose_name='Nota fiscal')),
                ('chave_nfe', models.CharField(blank=True, db_index=True, max_length=44, verbose_name='Chave NF-e')),
                ('dt', models.CharField(blank=True, max_length=100, verbose_name='DT')),
                ('cnpj_proprietario', models.CharField(blank=True, max_length=30, verbose_name='CNPJ/CPF proprietário')),
                ('placa_cavalo', models.CharField(blank=True, max_length=10, verbose_name='Placa cavalo')),
                ('placa_carreta', models.CharField(blank=True, max_length=10, verbose_name='Placa carreta')),
                ('motorista', models.CharField(blank=True, max_length=200, verbose_name='Motorista')),
                ('pdf_storage_key', models.CharField(
                    blank=True,
                    help_text='Objeto no bucket para download do PDF deste CT-e (pasta ctes/).',
                    max_length=500,
                    verbose_name='Chave do PDF no MinIO',
                )),
                ('criado_em', models.DateTimeField(auto_now_add=True, verbose_name='Criado em')),
            ],
            options={
                'verbose_name': 'CT-e',
                'verbose_name_plural': 'CT-es',
                'ordering': ['-data_emissao', '-criado_em'],
            },
        ),
    ]
