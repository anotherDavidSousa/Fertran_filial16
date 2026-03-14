from django.db.models.signals import pre_save, post_save, pre_delete, post_delete
from django.dispatch import receiver
from datetime import date
from .models import Cavalo, Carreta, LogCarreta, Motorista, HistoricoGestor


@receiver(pre_save, sender=Cavalo)
def log_mudanca_cavalo(sender, instance, **kwargs):
    if not instance.pk:
        return
    try:
        cavalo_antigo = Cavalo.objects.select_related('carreta', 'motorista', 'proprietario').get(pk=instance.pk)
        carreta_antiga = cavalo_antigo.carreta
        carreta_nova = instance.carreta
        if not carreta_antiga and carreta_nova:
            LogCarreta.objects.create(
                tipo='acoplamento',
                cavalo=instance,
                carreta_nova=carreta_nova.placa if carreta_nova else None,
                placa_cavalo=instance.placa,
                descricao=f'Carreta {carreta_nova.placa if carreta_nova else "N/A"} acoplada ao cavalo {instance.placa}',
            )
        elif carreta_antiga and not carreta_nova:
            LogCarreta.objects.create(
                tipo='desacoplamento',
                cavalo=instance,
                carreta_anterior=carreta_antiga.placa if carreta_antiga else None,
                placa_cavalo=instance.placa,
                descricao=f'Carreta {carreta_antiga.placa if carreta_antiga else "N/A"} desacoplada do cavalo {instance.placa}',
            )
        elif carreta_antiga and carreta_nova and carreta_antiga.pk != carreta_nova.pk:
            LogCarreta.objects.create(
                tipo='troca',
                cavalo=instance,
                carreta_anterior=carreta_antiga.placa if carreta_antiga else None,
                carreta_nova=carreta_nova.placa if carreta_nova else None,
                placa_cavalo=instance.placa,
                descricao=f'Troca de carreta no cavalo {instance.placa}: {carreta_antiga.placa if carreta_antiga else "N/A"} → {carreta_nova.placa if carreta_nova else "N/A"}',
            )
        try:
            motorista_antigo = cavalo_antigo.motorista
        except Motorista.DoesNotExist:
            motorista_antigo = None
        try:
            motorista_novo = instance.motorista
        except Motorista.DoesNotExist:
            motorista_novo = None
        if not motorista_antigo and motorista_novo:
            LogCarreta.objects.create(
                tipo='motorista_adicionado',
                cavalo=instance,
                motorista_novo=motorista_novo.nome if motorista_novo else None,
                placa_cavalo=instance.placa,
                descricao=f'Motorista {motorista_novo.nome if motorista_novo else "N/A"} adicionado ao cavalo {instance.placa}',
            )
        elif motorista_antigo and not motorista_novo:
            LogCarreta.objects.create(
                tipo='motorista_removido',
                cavalo=instance,
                motorista_anterior=motorista_antigo.nome if motorista_antigo else None,
                placa_cavalo=instance.placa,
                descricao=f'Motorista {motorista_antigo.nome if motorista_antigo else "N/A"} removido do cavalo {instance.placa}',
            )
        elif motorista_antigo and motorista_novo and motorista_antigo.pk != motorista_novo.pk:
            LogCarreta.objects.create(
                tipo='motorista_alterado',
                cavalo=instance,
                motorista_anterior=motorista_antigo.nome if motorista_antigo else None,
                motorista_novo=motorista_novo.nome if motorista_novo else None,
                placa_cavalo=instance.placa,
                descricao=f'Troca de motorista no cavalo {instance.placa}: {motorista_antigo.nome if motorista_antigo else "N/A"} → {motorista_novo.nome if motorista_novo else "N/A"}',
            )
        gestor_antigo = cavalo_antigo.gestor
        gestor_novo = instance.gestor
        if gestor_antigo != gestor_novo:
            if gestor_antigo and not gestor_novo:
                historico_aberto = HistoricoGestor.objects.filter(
                    gestor=gestor_antigo, cavalo=instance, data_fim__isnull=True
                ).first()
                if historico_aberto:
                    historico_aberto.data_fim = date.today()
                    historico_aberto.save()
            elif not gestor_antigo and gestor_novo:
                HistoricoGestor.objects.create(gestor=gestor_novo, cavalo=instance, data_inicio=date.today())
            elif gestor_antigo and gestor_novo and gestor_antigo.pk != gestor_novo.pk:
                historico_aberto = HistoricoGestor.objects.filter(
                    gestor=gestor_antigo, cavalo=instance, data_fim__isnull=True
                ).first()
                if historico_aberto:
                    historico_aberto.data_fim = date.today()
                    historico_aberto.save()
                HistoricoGestor.objects.create(gestor=gestor_novo, cavalo=instance, data_inicio=date.today())
        proprietario_antigo = cavalo_antigo.proprietario
        proprietario_novo = instance.proprietario
        if proprietario_antigo != proprietario_novo:
            if proprietario_antigo and proprietario_novo and proprietario_antigo.pk != proprietario_novo.pk:
                LogCarreta.objects.create(
                    tipo='troca_proprietario',
                    cavalo=instance,
                    proprietario_anterior=proprietario_antigo.nome_razao_social if proprietario_antigo else None,
                    proprietario_novo=proprietario_novo.nome_razao_social if proprietario_novo else None,
                    placa_cavalo=instance.placa,
                    descricao=f'Troca de proprietário no cavalo {instance.placa}: {proprietario_antigo.nome_razao_social if proprietario_antigo else "N/A"} → {proprietario_novo.nome_razao_social if proprietario_novo else "N/A"}',
                )
            elif proprietario_antigo and not proprietario_novo:
                LogCarreta.objects.create(
                    tipo='proprietario_alterado',
                    cavalo=instance,
                    proprietario_anterior=proprietario_antigo.nome_razao_social if proprietario_antigo else None,
                    placa_cavalo=instance.placa,
                    descricao=f'Proprietário removido do cavalo {instance.placa}: {proprietario_antigo.nome_razao_social if proprietario_antigo else "N/A"}',
                )
            elif not proprietario_antigo and proprietario_novo:
                LogCarreta.objects.create(
                    tipo='proprietario_alterado',
                    cavalo=instance,
                    proprietario_novo=proprietario_novo.nome_razao_social if proprietario_novo else None,
                    placa_cavalo=instance.placa,
                    descricao=f'Proprietário adicionado ao cavalo {instance.placa}: {proprietario_novo.nome_razao_social if proprietario_novo else "N/A"}',
                )
    except Cavalo.DoesNotExist:
        pass


@receiver(post_save, sender=Cavalo)
def atualizar_status_parceiro_apos_salvar_cavalo(sender, instance, created, **kwargs):
    if instance.proprietario:
        instance.proprietario.atualizar_status_automatico()
    if created and instance.gestor:
        HistoricoGestor.objects.create(gestor=instance.gestor, cavalo=instance, data_inicio=date.today())
    try:
        from .google_sheets import update_cavalo_async, add_cavalo_async
        if created:
            add_cavalo_async(instance.pk)
        else:
            update_cavalo_async(instance.pk)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Erro ao sincronizar com Google Sheets: {str(e)}")


@receiver(post_delete, sender=Cavalo)
def atualizar_status_parceiro_apos_deletar_cavalo(sender, instance, **kwargs):
    if instance.proprietario:
        instance.proprietario.atualizar_status_automatico()
    try:
        from .google_sheets import delete_cavalo_async
        if instance.placa:
            delete_cavalo_async(instance.placa)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Erro ao sincronizar com Google Sheets: {str(e)}")


@receiver(pre_save, sender=Motorista)
def log_mudanca_motorista(sender, instance, **kwargs):
    if instance.pk:
        try:
            motorista_antigo = Motorista.objects.select_related('cavalo').get(pk=instance.pk)
            instance._cavalo_antigo = motorista_antigo.cavalo
            cavalo_antigo = motorista_antigo.cavalo
            cavalo_novo = instance.cavalo
            if cavalo_antigo and not cavalo_novo:
                LogCarreta.objects.create(
                    tipo='motorista_removido',
                    cavalo=cavalo_antigo,
                    motorista_anterior=motorista_antigo.nome if motorista_antigo else None,
                    placa_cavalo=cavalo_antigo.placa if cavalo_antigo else None,
                    descricao=f'Motorista {motorista_antigo.nome if motorista_antigo else "N/A"} removido do cavalo {cavalo_antigo.placa if cavalo_antigo else "N/A"}',
                )
            elif not cavalo_antigo and cavalo_novo:
                LogCarreta.objects.create(
                    tipo='motorista_adicionado',
                    cavalo=cavalo_novo,
                    motorista_novo=instance.nome if instance else None,
                    placa_cavalo=cavalo_novo.placa if cavalo_novo else None,
                    descricao=f'Motorista {instance.nome if instance else "N/A"} adicionado ao cavalo {cavalo_novo.placa if cavalo_novo else "N/A"}',
                )
            elif cavalo_antigo and cavalo_novo and cavalo_antigo.pk != cavalo_novo.pk:
                LogCarreta.objects.create(
                    tipo='motorista_alterado',
                    cavalo=cavalo_novo,
                    motorista_anterior=cavalo_antigo.nome if cavalo_antigo else None,
                    motorista_novo=instance.nome if instance else None,
                    placa_cavalo=cavalo_novo.placa if cavalo_novo else None,
                    descricao=f'Motorista {instance.nome if instance else "N/A"} transferido do cavalo {cavalo_antigo.placa if cavalo_antigo else "N/A"} para o cavalo {cavalo_novo.placa if cavalo_novo else "N/A"}',
                )
        except Motorista.DoesNotExist:
            instance._cavalo_antigo = None
    else:
        instance._cavalo_antigo = None


@receiver(post_save, sender=Motorista)
def sincronizar_cavalo_apos_mudanca_motorista(sender, instance, created, **kwargs):
    try:
        cavalo_antigo = getattr(instance, '_cavalo_antigo', None)
        cavalo_novo = instance.cavalo
        if cavalo_novo and cavalo_novo.pk:
            try:
                from .google_sheets import update_cavalo_async
                update_cavalo_async(cavalo_novo.pk)
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(f"Erro ao chamar update_cavalo_async: {str(e)}")
        if cavalo_antigo and cavalo_antigo != cavalo_novo and cavalo_antigo.pk:
            try:
                from .google_sheets import update_cavalo_async
                update_cavalo_async(cavalo_antigo.pk)
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(f"Erro ao chamar update_cavalo_async (cavalo antigo): {str(e)}")
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Erro ao sincronizar cavalo após mudança de motorista: {str(e)}")


@receiver(pre_delete, sender=Motorista)
def _guardar_cavalo_para_sync_motorista(sender, instance, **kwargs):
    """Guarda o cavalo do motorista para atualizar a planilha após o delete."""
    instance._cavalo_pk_para_sheets = getattr(instance, 'cavalo_id', None)


@receiver(post_delete, sender=Motorista)
def sincronizar_planilha_apos_deletar_motorista(sender, instance, **kwargs):
    try:
        from .google_sheets import update_cavalo_async
        cavalo_pk = getattr(instance, '_cavalo_pk_para_sheets', None)
        if cavalo_pk:
            update_cavalo_async(cavalo_pk)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Erro ao sincronizar planilha após deletar motorista: {str(e)}")


@receiver(post_save, sender=Carreta)
def sincronizar_planilha_apos_salvar_carreta(sender, instance, created, **kwargs):
    """Quando uma carreta é criada ou alterada, atualiza o cavalo que a usa na planilha."""
    try:
        from .google_sheets import update_cavalo_async
        cavalo = getattr(instance, 'cavalo_acoplado', None)
        if cavalo:
            update_cavalo_async(cavalo.pk)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Erro ao sincronizar planilha após salvar carreta: {str(e)}")


@receiver(pre_delete, sender=Carreta)
def _guardar_cavalos_para_sync_carreta(sender, instance, **kwargs):
    """Antes de deletar a carreta, guarda os PKs dos cavalos que a usam (para atualizar a planilha)."""
    instance._cavalo_pks_para_sheets = list(
        Cavalo.objects.filter(carreta=instance).values_list('pk', flat=True)
    )


@receiver(post_delete, sender=Carreta)
def sincronizar_planilha_apos_deletar_carreta(sender, instance, **kwargs):
    """Após deletar a carreta, os cavalos que a usavam ficam com carreta=None; atualiza a planilha."""
    try:
        from .google_sheets import update_cavalo_async
        for cavalo_pk in getattr(instance, '_cavalo_pks_para_sheets', []) or []:
            update_cavalo_async(cavalo_pk)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Erro ao sincronizar planilha após deletar carreta: {str(e)}")
