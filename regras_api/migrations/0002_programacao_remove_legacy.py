# Generated manually — substitui modelos antigos por Programacao

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('regras_api', '0001_initial'),
    ]

    operations = [
        migrations.DeleteModel(name='Produto'),
        migrations.DeleteModel(name='RegraFaturamento'),
        migrations.DeleteModel(name='RegraPagador'),
        migrations.DeleteModel(name='RegraPeso'),
        migrations.DeleteModel(name='RegraTerminal'),
        migrations.DeleteModel(name='RegraValor'),
        migrations.DeleteModel(name='Rota'),
        migrations.CreateModel(
            name='Programacao',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('cnpj_emit', models.CharField(db_index=True, max_length=20)),
                ('cnpj_dest', models.CharField(db_index=True, max_length=20)),
                (
                    'pagador',
                    models.CharField(
                        db_index=True,
                        help_text='0=remetente paga, 1=destinatário paga (modFrete na NF-e)',
                        max_length=1,
                    ),
                ),
                ('codigo', models.CharField(help_text='Identificador da programação (ex.: PRG001)', max_length=40)),
                (
                    'tipo_faturamento',
                    models.CharField(
                        choices=[
                            ('ordem_de_servico', 'Ordem de serviço'),
                            ('conhecimento_de_transporte', 'Conhecimento de transporte'),
                        ],
                        default='conhecimento_de_transporte',
                        max_length=40,
                    ),
                ),
                (
                    'campo_peso',
                    models.CharField(
                        default='pesoL',
                        help_text='pesoL | pesoqCom | pesoB | atlas_prod (atributos DadosXML)',
                        max_length=40,
                    ),
                ),
                (
                    'campo_valor',
                    models.CharField(
                        default='vLiq',
                        help_text='vLiq | vProd',
                        max_length=40,
                    ),
                ),
                (
                    'fornecedor_vale_pedagio',
                    models.CharField(
                        blank=True,
                        help_text='Código do fornecedor de vale pedágio; vazio = não enviar no JSON',
                        max_length=50,
                    ),
                ),
                ('atualizado_em', models.DateTimeField(auto_now=True)),
                ('criado_em', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'verbose_name': 'Programação',
                'verbose_name_plural': 'Programações',
                'ordering': ['cnpj_emit', 'cnpj_dest', 'pagador'],
            },
        ),
        migrations.AddConstraint(
            model_name='programacao',
            constraint=models.UniqueConstraint(
                fields=('cnpj_emit', 'cnpj_dest', 'pagador'),
                name='uq_programacao_emit_dest_pagador',
            ),
        ),
    ]
