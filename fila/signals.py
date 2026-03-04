"""
Signals para vincular automaticamente OST e Carregamento.
Match sempre por: Nota fiscal + Chave de acesso (OST.nota_fiscal é list/JSON).
"""
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.utils import timezone

from .models import Carregamento, OST


def _chave_normalizada(val):
    """Chave de acesso para comparação: strip + só dígitos."""
    if not val:
        return ''
    s = str(val).strip()
    return ''.join(c for c in s if c.isdigit()) or s


def _nota_fiscal_bate(carregamento_nota, ost_nota_fiscal):
    """
    True se a nota do carregamento bate com alguma do campo OST.nota_fiscal (objeto/list).
    ost_nota_fiscal: valor do campo nota_fiscal da OST (list ou valor único).
    """
    if carregamento_nota is None or carregamento_nota == '':
        return False
    cn = str(carregamento_nota).strip()
    if not cn:
        return False
    if ost_nota_fiscal is None:
        return False
    if isinstance(ost_nota_fiscal, list):
        for nf in ost_nota_fiscal:
            if str(nf).strip() == cn:
                return True
        return False
    return str(ost_nota_fiscal).strip() == cn


def _match_nf_e_chave(carregamento, ost):
    """True se Carregamento e OST batem por Nota fiscal + Chave de acesso."""
    if not _nota_fiscal_bate(carregamento.nota_fiscal, ost.nota_fiscal):
        return False
    c_norm = _chave_normalizada(carregamento.chave_acesso)
    o_norm = _chave_normalizada(ost.chave_acesso)
    if not c_norm or not o_norm:
        return False
    return c_norm == o_norm


def _vincular_ost_carregamento(ost, carregamento):
    """Vincula a OST ao carregamento e marca como manifestado."""
    carregamento.ost = ost
    carregamento.arquivado = True
    if not carregamento.manifestado_em:
        carregamento.manifestado_em = timezone.now()
    carregamento.save(update_fields=['ost', 'arquivado', 'manifestado_em', 'atualizado_em'])


def _encontrar_carregamento_para_ost(ost):
    """Retorna um Carregamento que bata com a OST (Nota fiscal + Chave de acesso). Prioriza fila (sem OST)."""
    ost_chave_norm = _chave_normalizada(ost.chave_acesso)
    if not ost_chave_norm:
        return None
    # 1) Busca direta por chave exata (inclui itens na fila e já manifestados sem OST)
    for c in Carregamento.objects.filter(ost__isnull=True, chave_acesso=ost_chave_norm):
        if _nota_fiscal_bate(c.nota_fiscal, ost.nota_fiscal):
            return c
    # 2) Chave pode ter espaços no banco: percorre sem OST e compara normalizado
    for c in Carregamento.objects.filter(ost__isnull=True)[:5000]:
        if _match_nf_e_chave(c, ost):
            return c
    # 3) Qualquer carregamento com match (já vinculado a outra OST; permite trocar)
    for c in Carregamento.objects.filter(chave_acesso=ost_chave_norm):
        if _nota_fiscal_bate(c.nota_fiscal, ost.nota_fiscal):
            return c
    return None


def _encontrar_ost_para_carregamento(carregamento):
    """Retorna uma OST que bata com o Carregamento (Nota fiscal + Chave de acesso). Prefere OST com PDF."""
    c_norm = _chave_normalizada(carregamento.chave_acesso)
    if not c_norm:
        return None
    # 1) Busca direta por chave exata
    com_pdf = []
    sem_pdf = []
    for ost in OST.objects.filter(chave_acesso=c_norm):
        if not _nota_fiscal_bate(carregamento.nota_fiscal, ost.nota_fiscal):
            continue
        if ost.pdf_storage_key:
            com_pdf.append(ost)
        else:
            sem_pdf.append(ost)
    if com_pdf or sem_pdf:
        return com_pdf[0] if com_pdf else sem_pdf[0]
    # 2) Fallback: percorre e compara normalizado (chave com espaço no banco)
    for ost in OST.objects.all()[:5000]:
        if _match_nf_e_chave(carregamento, ost):
            return ost
    return None


def tentar_vincular_fila_a_osts(limite=150):
    """
    Varredura manual: para carregamentos na fila (arquivado=False) sem OST,
    tenta encontrar OST por Nota fiscal + Chave de acesso e vincular.
    Use quando os XMLs forem inseridos fora do Django (ex.: n8n direto no banco),
    pois nesse caso post_save não dispara.
    Retorna quantos foram vinculados.
    """
    vinculados = 0
    for c in Carregamento.objects.filter(arquivado=False, ost__isnull=True)[:limite]:
        ost = _encontrar_ost_para_carregamento(c)
        if ost:
            _vincular_ost_carregamento(ost, c)
            vinculados += 1
    return vinculados


@receiver(post_save, sender=Carregamento, dispatch_uid='fila.carregamento_vincular_ost')
def carregamento_post_save_vincular_ost(sender, instance, created, **kwargs):
    """Ao salvar Carregamento sem OST, tenta encontrar OST por Nota fiscal + Chave de acesso."""
    if instance.ost_id is not None:
        return
    ost = _encontrar_ost_para_carregamento(instance)
    if ost:
        _vincular_ost_carregamento(ost, instance)


@receiver(post_save, sender=OST, dispatch_uid='fila.ost_vincular_carregamento')
def ost_post_save_vincular_carregamento(sender, instance, created, **kwargs):
    """Ao salvar OST, tenta encontrar Carregamento por Nota fiscal + Chave de acesso e vincular."""
    # Só tenta se esta OST ainda não tem nenhum carregamento vinculado (opcional: podemos sempre tentar e atualizar)
    if instance.carregamentos.exists():
        return
    carregamento = _encontrar_carregamento_para_ost(instance)
    if carregamento:
        _vincular_ost_carregamento(instance, carregamento)
