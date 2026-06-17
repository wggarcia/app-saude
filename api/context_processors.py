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
        from .access_control import contexto_navegacao_setorial
        ctx = contexto_navegacao_setorial(request)
    except Exception:
        ctx = {
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
        }

    try:
        from .access_control import empresa_tem_feature, perfil_principal
        empresa = getattr(request, "empresa", None)
        ctx["tem_assistente_ia"] = bool(empresa and empresa_tem_feature(empresa, "sst.assistente_ia"))
        pf = perfil_principal(request)
        ctx["perfil_usuario_sst"] = pf
        # Grupos de visibilidade para o sidebar SST (sem perfil = mostra tudo)
        sem_perfil = pf in ("gerencia", "operacao") or not pf
        ctx["pf_ver_nucleo"]     = sem_perfil or pf in ("admin", "gestor", "medico", "tecnico_sesmt", "auxiliar", "rh")
        ctx["pf_ver_funcionario"] = sem_perfil or pf in ("admin", "gestor", "rh")
        ctx["pf_ver_aso"]        = sem_perfil or pf in ("admin", "gestor", "medico")
        ctx["pf_ver_agenda"]     = sem_perfil or pf in ("admin", "gestor", "medico", "auxiliar")
        ctx["pf_ver_legal"]      = sem_perfil or pf in ("admin", "gestor", "rh", "tecnico_sesmt", "medico")
        ctx["pf_ver_afastamento"] = sem_perfil or pf in ("admin", "gestor", "rh", "medico")
        ctx["pf_ver_cat"]        = sem_perfil or pf in ("admin", "gestor", "tecnico_sesmt", "rh")
        ctx["pf_ver_esocial"]    = sem_perfil or pf in ("admin", "gestor", "rh")
        ctx["pf_ver_postos"]     = sem_perfil or pf in ("admin", "gestor", "tecnico_sesmt")
        ctx["pf_ver_prevencao"]  = sem_perfil or pf in ("admin", "gestor", "medico", "tecnico_sesmt")
        ctx["pf_ver_riscos"]     = sem_perfil or pf in ("admin", "gestor", "tecnico_sesmt")
        ctx["pf_ver_epi"]        = sem_perfil or pf in ("admin", "gestor", "tecnico_sesmt")
        ctx["pf_ver_saude"]      = sem_perfil or pf in ("admin", "gestor", "medico")
        ctx["pf_ver_governanca"] = sem_perfil or pf in ("admin", "gestor")
        ctx["pf_ver_config"]     = sem_perfil or pf in ("admin", "ti", "gestor")
        ctx["pf_ver_ti_link"]    = sem_perfil or pf in ("admin", "ti")
    except Exception:
        ctx["tem_assistente_ia"] = False
        ctx["perfil_usuario_sst"] = ""
        for k in ("pf_ver_nucleo", "pf_ver_funcionario", "pf_ver_aso", "pf_ver_agenda",
                  "pf_ver_legal", "pf_ver_afastamento", "pf_ver_cat", "pf_ver_esocial",
                  "pf_ver_postos", "pf_ver_prevencao", "pf_ver_riscos", "pf_ver_epi",
                  "pf_ver_saude", "pf_ver_governanca", "pf_ver_config", "pf_ver_ti_link"):
            ctx[k] = True  # fallback: mostra tudo

    return ctx
