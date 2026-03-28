from .models import Pendencia


def wpp_pendencias(request):
    """Injects the count of open WPP pendências for the sidebar badge."""
    if not request.user.is_authenticated:
        return {'wpp_pendencias_abertas': 0}
    try:
        count = Pendencia.objects.filter(status=Pendencia.STATUS_ABERTA).count()
    except Exception:
        count = 0
    return {'wpp_pendencias_abertas': count}
