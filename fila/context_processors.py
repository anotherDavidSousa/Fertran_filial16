from .models import Carregamento
from .menu_perms import user_menu_permissions


def total_fila(request):
    """Injeta o total de notas na fila (aba geral) para o menu lateral."""
    return {
        'total_fila': Carregamento.objects.filter(arquivado=False).count(),
    }


def menu_permissions(request):
    """Permissões de menu por grupo: administradores veem tudo; Operadores só Fila, Manifestados, Cavalos."""
    if not request.user.is_authenticated:
        return {
            'can_see_home': False,
            'can_see_fila': False,
            'can_see_processador': False,
            'can_see_cavalos': False,
            'can_see_agregamento': False,
        }
    return user_menu_permissions(request.user)
