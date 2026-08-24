"""
face_warmup.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Aquecimento do motor de reconhecimento facial (VITA OS).

A primeira chamada do DeepFace em cada processo (worker gunicorn) carrega os
modelos ArcFace + RetinaFace na memória — o que leva 15-30s e faz a 1ª
detecção parecer "travada". Aqui pré-carregamos os modelos em background no
boot de cada worker, para que a primeira detecção real já seja rápida.

Roda só quando o app está SERVINDO (gunicorn/runserver) — nunca em migrate,
shell, testes, etc. — e sempre em thread daemon, sem bloquear o boot.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
from __future__ import annotations

import logging
import os
import sys
import threading

logger = logging.getLogger(__name__)

_ja_aqueceu = False

# Comandos em que NÃO se deve aquecer (não estão servindo requisições)
_COMANDOS_SEM_WARMUP = {
    "migrate", "makemigrations", "shell", "shell_plus", "test", "collectstatic",
    "createsuperuser", "dumpdata", "loaddata", "check", "showmigrations",
    "sqlmigrate", "createcachetable", "compilemessages", "makemessages",
}


def _deve_aquecer() -> bool:
    if os.environ.get("VITA_FACE_WARMUP", "1") == "0":
        return False
    argv = sys.argv or []
    for cmd in _COMANDOS_SEM_WARMUP:
        if cmd in argv:
            return False
    return True


def _aquecer():
    try:
        import numpy as np
        from deepface import DeepFace
        # Imagem em branco só para forçar o load dos pesos (sem exigir rosto).
        img = np.zeros((160, 160, 3), dtype=np.uint8)
        DeepFace.represent(
            img_path=img,
            model_name="ArcFace",
            detector_backend="retinaface",
            enforce_detection=False,
            align=False,
        )
        logger.info("VITA face warmup: ArcFace + RetinaFace carregados.")
    except Exception as exc:  # best-effort — nunca derruba o worker
        logger.warning("VITA face warmup falhou (segue lazy): %s", exc)


def iniciar_warmup():
    """Dispara o aquecimento em thread daemon, uma vez por processo."""
    global _ja_aqueceu
    if _ja_aqueceu or not _deve_aquecer():
        return
    _ja_aqueceu = True
    threading.Thread(target=_aquecer, name="vita-face-warmup", daemon=True).start()
