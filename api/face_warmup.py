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


def _deve_aquecer() -> bool:
    # Lista de permissão, não de bloqueio: cada processo aquecido ocupa ~1,3 GB.
    # A lista de bloqueio antiga deixava todo comando de cron e o rqworker
    # carregarem o modelo, e isso esgotou a RAM do VPS (quedas de nov/2026).
    if os.environ.get("VITA_FACE_WARMUP", "1") == "0":
        return False
    argv = sys.argv or []
    executavel = os.path.basename(argv[0]) if argv else ""
    return "gunicorn" in executavel or "runserver" in argv


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
