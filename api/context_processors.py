from django.conf import settings


def public_settings(request):
    return {
        "MAPBOX_ACCESS_TOKEN": settings.MAPBOX_ACCESS_TOKEN,
        "GOOGLE_MAPS_BROWSER_KEY": settings.GOOGLE_MAPS_BROWSER_KEY,
        "PUBLIC_BASE_URL": settings.PUBLIC_BASE_URL,
        "ALLOW_ENTERPRISE_DEMO_MUTATIONS": getattr(settings, "ALLOW_ENTERPRISE_DEMO_MUTATIONS", False),
    }


def profile_navigation(request):
    try:
        from .access_control import contexto_navegacao_setorial, empresa_tem_feature

        ctx = contexto_navegacao_setorial(request)
        empresa = getattr(request, "empresa", None)
        ctx["tem_assistente_ia"] = bool(empresa and empresa_tem_feature(empresa, "sst.assistente_ia"))
        return ctx
    except Exception:
        return {
            "setor_atual": "empresa",
            "perfil_principal": "operacao",
            "acesso_ti": False,
            "acesso_gerencia": False,
            "acesso_rh": False,
            "acesso_operacao": False,
            "mostrar_link_ti": False,
            "mostrar_link_rh": False,
            "mostrar_aba_gerencia": False,
            "portal_ti_url": "/ti/",
            "gerencia_url": "/gerencia/",
            "rh_url": "/rh/",
            "tem_assistente_ia": False,
        }
