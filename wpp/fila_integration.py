"""
Integration between the wpp app and the fila app.
The wpp app imports from fila; fila is never modified.
"""
import logging

logger = logging.getLogger(__name__)


def tentar_arquivar_carregamento(grupo) -> bool:
    """
    Archives the active Carregamento linked to `grupo` via placa_cavalo.
    Returns True if at least one Carregamento was archived, False otherwise.
    """
    if not grupo or not grupo.placa_cavalo:
        return False

    from fila.models import Carregamento, OST

    ost_ids = list(
        OST.objects.filter(placa_cavalo__iexact=grupo.placa_cavalo)
        .values_list('id', flat=True)
    )
    if not ost_ids:
        return False

    updated = Carregamento.objects.filter(
        ost_id__in=ost_ids, arquivado=False
    ).update(arquivado=True)

    if updated:
        logger.info(
            'Arquivados %d Carregamento(s) para placa %s (grupo %s)',
            updated, grupo.placa_cavalo, grupo.jid,
        )
        return True

    return False
