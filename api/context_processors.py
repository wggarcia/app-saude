from django.conf import settings


def public_settings(request):
    return {
        "MAPBOX_ACCESS_TOKEN": settings.MAPBOX_ACCESS_TOKEN,
        "GOOGLE_MAPS_BROWSER_KEY": settings.GOOGLE_MAPS_BROWSER_KEY,
        "PUBLIC_BASE_URL": settings.PUBLIC_BASE_URL,
    }
