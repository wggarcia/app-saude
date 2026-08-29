"""
Middleware de roteamento por subdomínio.

Mapeia subdomínios públicos → paths internos do app, sem expor "admin" na URL.

    paciente.solocrt.com.br        → /paciente/
    vita.solocrt.com.br            → /hospital/vita/
    vita.solocrt.com.br/totem/     → já está correto (sem redirect)
"""
from django.http import HttpResponsePermanentRedirect


SUBDOMAIN_ROOT_MAP = {
    "paciente": "/paciente/",
    "vita":     "/hospital/vita/",
}


class SubdomainRoutingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        host = request.get_host().split(":")[0].lower()
        subdomain = host.split(".")[0]

        if subdomain in SUBDOMAIN_ROOT_MAP and request.path in ("/", ""):
            return HttpResponsePermanentRedirect(SUBDOMAIN_ROOT_MAP[subdomain])

        return self.get_response(request)
