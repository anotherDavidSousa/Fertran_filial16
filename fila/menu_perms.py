"""
Controle de menus por grupo: administradores veem tudo; grupo Operadores só Fila, Manifestados e Cavalos.
"""
from functools import wraps
from django.shortcuts import redirect
from django.http import HttpResponseForbidden

# Nome do grupo com acesso limitado (apenas Fila, Manifestados, Cavalos)
GROUP_OPERADORES = 'Operadores'
# Nome do grupo com acesso ao módulo WhatsApp
GROUP_OPERADORES_WPP = 'Operadores WPP'


def _user_has_full_access(user):
    """Administradores têm acesso total."""
    if not user or not user.is_authenticated:
        return False
    return user.is_staff or user.is_superuser


def _user_is_operador(user):
    """Pertence ao grupo com acesso limitado."""
    if not user or not user.is_authenticated:
        return False
    return user.groups.filter(name=GROUP_OPERADORES).exists()


def _user_is_operador_wpp(user):
    """Pertence ao grupo com acesso ao módulo WhatsApp."""
    if not user or not user.is_authenticated:
        return False
    return user.groups.filter(name=GROUP_OPERADORES_WPP).exists()


def user_menu_permissions(user):
    """
    Retorna um dicionário com as permissões de menu para o usuário.
    - Acesso total (is_staff/is_superuser): todos True.
    - Grupo Operadores: Home, Fila, Manifestados, Cavalos (sem Processador, sem resto do Agregamento).
    - Outros usuários autenticados: apenas Home (demais False).
    """
    perms = {
        'can_see_home': True,
        'can_see_fila': False,
        'can_see_processador': False,
        'can_see_cavalos': False,
        'can_see_agregamento': False,  # Dashboard, Carretas, Motoristas, Proprietários, Gestores, Logs
        'can_see_wpp': False,
    }
    if not user or not user.is_authenticated:
        perms['can_see_home'] = False
        return perms
    if _user_has_full_access(user):
        perms['can_see_fila'] = True
        perms['can_see_processador'] = True
        perms['can_see_cavalos'] = True
        perms['can_see_agregamento'] = True
        perms['can_see_wpp'] = True
        return perms
    if _user_is_operador(user):
        perms['can_see_fila'] = True
        perms['can_see_cavalos'] = True
    if _user_is_operador_wpp(user):
        perms['can_see_wpp'] = True
    return perms


def user_can_access(user, permission):
    """True se o usuário pode acessar a área (fila, processador, cavalos, agregamento)."""
    if not user or not user.is_authenticated:
        return False
    if _user_has_full_access(user):
        return True
    perms = user_menu_permissions(user)
    return perms.get(f'can_see_{permission}', False)


def require_menu_perm(permission):
    """
    Decorator: exige permissão de menu (fila, processador, cavalos, agregamento).
    Deve ser usado junto com @login_required (aplicar por último).
    """
    def decorator(view_func):
        @wraps(view_func)
        def _wrapped_view(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('login')
            if user_can_access(request.user, permission):
                return view_func(request, *args, **kwargs)
            return HttpResponseForbidden(
                '<h1>403 Acesso negado</h1><p>Você não tem permissão para acessar esta página.</p>'
            )
        return _wrapped_view
    return decorator
