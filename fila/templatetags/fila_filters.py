from django import template
from django.template.defaultfilters import stringfilter

register = template.Library()


@register.filter
@stringfilter
def remetente_short(value):
    """Exibe só a parte após ' - ' (ex.: 'X S/A - USIMINAS' -> 'USIMINAS')."""
    if not value or value.strip() == '—':
        return value or '—'
    if ' - ' in value:
        return value.split(' - ')[-1].strip()
    return value


@register.filter
def peso_format(value):
    """Formata peso como 26.460kg (inteiro com ponto como separador de milhar)."""
    if value is None:
        return '—'
    try:
        n = int(float(value))
        return f'{n:,}'.replace(',', '.') + 'kg'
    except (ValueError, TypeError):
        return str(value) + ' kg' if value else '—'


@register.filter
def extra_label(key):
    """Converte chave do extra em título de exibição (com emoji quando aplicável)."""
    labels = {
        'doc_transp': '📋 Documento de transporte',
        'motorista': '👷‍♂️ Motorista',
    }
    return labels.get(key, key.replace('_', ' ').title())


@register.filter
def get_extra(extras, key):
    """Retorna o valor do extra pela chave (case-insensitive), ou string vazia se não existir."""
    if not extras or not isinstance(extras, dict):
        return ''
    key_lower = str(key).lower()
    for k, v in extras.items():
        if str(k).lower() == key_lower:
            return v
    return ''
