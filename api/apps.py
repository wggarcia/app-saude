from django.apps import AppConfig


class ApiConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'api'

    def ready(self):
        import api.signals  # noqa: F401 — registra os signals FCM
        # Aquece o modelo facial (ArcFace/RetinaFace) em background no boot do
        # worker, pra 1ª detecção do VITA OS não travar ~15-30s carregando.
        try:
            from api.face_warmup import iniciar_warmup
            iniciar_warmup()
        except Exception:
            pass
