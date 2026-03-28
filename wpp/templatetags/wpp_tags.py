import re
from datetime import timedelta

from django import template
from django.utils import timezone
from django.utils.html import conditional_escape, mark_safe

register = template.Library()

_AVATAR_COLORS = [
    '#1a6b5e', '#2d6a9f', '#6d3b8e', '#8e3b3b', '#3b6d4b',
    '#8e5c2d', '#2d4f8e', '#6d1a6b', '#1a5c6d', '#5c6d1a',
]


@register.filter
def avatar_color(value):
    """Deterministic avatar background colour from any string."""
    h = sum(ord(c) for c in str(value)) if value else 0
    return _AVATAR_COLORS[h % len(_AVATAR_COLORS)]


@register.filter
def wpp_format(value):
    """Convert WhatsApp markdown (*bold*, _italic_, ~strike~) to safe HTML."""
    text = conditional_escape(str(value or ''))
    text = re.sub(r'\*([^*\n]+)\*', r'<strong>\1</strong>', text)
    text = re.sub(r'_([^_\n]+)_', r'<em>\1</em>', text)
    text = re.sub(r'~([^~\n]+)~', r'<s>\1</s>', text)
    text = text.replace('\n', '<br>')
    return mark_safe(text)


@register.filter
def date_label(value):
    """Returns 'Hoje', 'Ontem', or dd/mm/yyyy."""
    try:
        today = timezone.localdate()
        d = value.date() if hasattr(value, 'date') else value
        if d == today:
            return 'Hoje'
        if d == today - timedelta(days=1):
            return 'Ontem'
        return d.strftime('%d/%m/%Y')
    except Exception:
        return str(value)


@register.filter
def basename(value):
    """Returns the filename portion of a storage key or URL."""
    if not value:
        return ''
    return str(value).rstrip('/').split('/')[-1].split('?')[0]


@register.filter
def wpp_time(value):
    """HH:MM in local timezone."""
    try:
        local = timezone.localtime(value)
        return local.strftime('%H:%M')
    except Exception:
        return ''
