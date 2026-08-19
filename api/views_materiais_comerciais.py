"""
views_materiais_comerciais.py
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Páginas públicas de material comercial (portfólio resumido + catálogo
completo de planos/módulos) para SST e Farmácia, linkadas nos emails de
prospecção. Páginas estáticas — sem dado de tenant, sem autenticação.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"""
from django.shortcuts import render


def portfolio_farmacia(request):
    return render(request, "materiais/portfolio_farmacia.html")


def catalogo_farmacia(request):
    return render(request, "materiais/catalogo_farmacia.html")


def portfolio_sst(request):
    return render(request, "materiais/portfolio_sst.html")


def catalogo_sst(request):
    return render(request, "materiais/catalogo_sst.html")
