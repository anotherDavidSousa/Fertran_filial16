def wpp_pendencias(request):
    """Injects the count of open WPP pendências for the sidebar badge.
    Fails silently if the wpp tables don't exist yet (migration not run).
    """
    if not request.user.is_authenticated:
        return {'wpp_pendencias_abertas': 0}
    try:
        from .models import Pendencia
        count = Pendencia.objects.filter(status=Pendencia.STATUS_ABERTA).count()
    except Exception:
        count = 0
    return {'wpp_pendencias_abertas': count}
