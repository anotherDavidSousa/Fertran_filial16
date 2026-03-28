from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.db.models.functions


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='WppInstance',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('nome', models.CharField(max_length=100, verbose_name='Nome')),
                ('token', models.CharField(max_length=200, verbose_name='Token UAZAPI')),
                ('ativo', models.BooleanField(default=True, verbose_name='Ativo')),
                ('criado_em', models.DateTimeField(auto_now_add=True, verbose_name='Criado em')),
            ],
            options={
                'verbose_name': 'Instância WPP',
                'verbose_name_plural': 'Instâncias WPP',
            },
        ),
        migrations.CreateModel(
            name='Contato',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('jid', models.CharField(db_index=True, help_text='Ex.: 5531999999999@s.whatsapp.net', max_length=100, unique=True, verbose_name='JID')),
                ('nome', models.CharField(blank=True, max_length=200, verbose_name='Nome')),
                ('telefone', models.CharField(blank=True, max_length=30, verbose_name='Telefone')),
                ('atualizado_em', models.DateTimeField(auto_now=True, verbose_name='Atualizado em')),
            ],
            options={
                'verbose_name': 'Contato',
                'verbose_name_plural': 'Contatos',
                'ordering': ['nome'],
            },
        ),
        migrations.CreateModel(
            name='GrupoConfig',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('jid', models.CharField(db_index=True, help_text='Ex.: 55319...@g.us', max_length=120, unique=True, verbose_name='JID')),
                ('nome', models.CharField(blank=True, max_length=300, verbose_name='Nome do grupo')),
                ('placa_cavalo', models.CharField(blank=True, db_index=True, help_text='Extraída automaticamente do nome do grupo ou preenchida manualmente.', max_length=10, verbose_name='Placa do cavalo')),
                ('ativo', models.BooleanField(default=True, verbose_name='Ativo')),
                ('sincronizado_em', models.DateTimeField(blank=True, null=True, verbose_name='Sincronizado em')),
                ('instance', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='grupos', to='wpp.wppinstance', verbose_name='Instância')),
            ],
            options={
                'verbose_name': 'Grupo',
                'verbose_name_plural': 'Grupos',
                'ordering': ['nome'],
            },
        ),
        migrations.CreateModel(
            name='Mensagem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('msg_id', models.CharField(db_index=True, max_length=100, unique=True, verbose_name='ID da mensagem')),
                ('jid_chat', models.CharField(db_index=True, help_text='JID do grupo ou contato onde a mensagem chegou.', max_length=120, verbose_name='JID chat')),
                ('sender_jid', models.CharField(blank=True, max_length=120, verbose_name='JID remetente')),
                ('sender_nome', models.CharField(blank=True, max_length=200, verbose_name='Nome remetente')),
                ('from_me', models.BooleanField(default=False, verbose_name='Enviada por nós')),
                ('tipo', models.CharField(choices=[('text', 'Texto'), ('image', 'Imagem'), ('document', 'Documento'), ('audio', 'Áudio'), ('video', 'Vídeo'), ('sticker', 'Sticker'), ('other', 'Outro')], default='text', max_length=20, verbose_name='Tipo')),
                ('texto', models.TextField(blank=True, verbose_name='Texto')),
                ('media_minio_key', models.CharField(blank=True, max_length=500, verbose_name='Chave MinIO da mídia')),
                ('timestamp', models.DateTimeField(db_index=True, verbose_name='Timestamp')),
                ('criado_em', models.DateTimeField(auto_now_add=True, db_default=django.db.models.functions.Now(), verbose_name='Criado em')),
                ('contato', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='mensagens', to='wpp.contato', verbose_name='Contato')),
                ('enviado_por', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='mensagens_wpp', to=settings.AUTH_USER_MODEL, verbose_name='Enviado por (usuário interno)')),
                ('grupo', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='mensagens', to='wpp.grupoconfig', verbose_name='Grupo')),
            ],
            options={
                'verbose_name': 'Mensagem',
                'verbose_name_plural': 'Mensagens',
                'ordering': ['timestamp'],
            },
        ),
        migrations.CreateModel(
            name='PerfilUsuario',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('assinatura', models.CharField(help_text='Ex.: João — será exibida em negrito no início da mensagem.', max_length=50, verbose_name='Assinatura')),
                ('user', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='wpp_perfil', to=settings.AUTH_USER_MODEL, verbose_name='Usuário')),
            ],
            options={
                'verbose_name': 'Perfil WPP',
                'verbose_name_plural': 'Perfis WPP',
            },
        ),
        migrations.CreateModel(
            name='Pendencia',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('texto', models.TextField(verbose_name='Descrição')),
                ('status', models.CharField(choices=[('aberta', 'Aberta'), ('resolvida', 'Resolvida')], db_index=True, default='aberta', max_length=20, verbose_name='Status')),
                ('criado_em', models.DateTimeField(auto_now_add=True, db_default=django.db.models.functions.Now(), verbose_name='Criado em')),
                ('resolvido_em', models.DateTimeField(blank=True, null=True, verbose_name='Resolvido em')),
                ('arquivou_carregamento', models.BooleanField(default=False, help_text='True se a resolução desta pendência causou o arquivamento de um Carregamento.', verbose_name='Arquivou carregamento?')),
                ('criado_por', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='pendencias_criadas', to=settings.AUTH_USER_MODEL, verbose_name='Criado por')),
                ('grupo', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='pendencias', to='wpp.grupoconfig', verbose_name='Grupo')),
                ('resolvido_por', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='pendencias_resolvidas', to=settings.AUTH_USER_MODEL, verbose_name='Resolvido por')),
            ],
            options={
                'verbose_name': 'Pendência',
                'verbose_name_plural': 'Pendências',
                'ordering': ['-criado_em'],
            },
        ),
    ]
