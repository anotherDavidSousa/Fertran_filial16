from .menu_perms import user_menu_permissions


def menu_permissions(request):
    if not request.user.is_authenticated:
        return {
            'can_see_home': False,
            'can_see_fila': False,
            'can_see_processador': False,
            'can_see_cavalos': False,
            'can_see_agregamento': False,
        }
    return user_menu_permissions(request.user)
