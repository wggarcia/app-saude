"""
Núcleo compartilhado do SUAS — serializadores usados pelos DOIS lados que
oferecem gestão social sobre os mesmos models:

  • Governo   (views_governo_suas_*)  — SUAS embutido no ambiente de saúde pública
  • Assistência isolada (views_assistencia_*) — produto vendido só p/ a secretaria social

As duas ofertas são intencionais (duas portas de entrada, dois logins/segmentos).
O que estava duplicado era o CÓDIGO. Este módulo centraliza a serialização dos
models compartilhados (UnidadeCRAS, FamiliaCRAS, VisitaDomiciliarSocial), de modo
que um ajuste de campo passe a valer para os dois lados de uma vez.

IMPORTANTE — o que NÃO mora aqui, de propósito:
  • `atendimento_dict`: os dois lados divergem (Governo expõe "tipo_display",
    Assistência não). Cada lado mantém o seu. Ver test_suas_caracterizacao.
  • O envelope de resposta (Governo usa {"total", ...}; Assistência não). Cada
    view monta o seu envelope; aqui só serializamos o item.

Coberto por api/test_suas_caracterizacao.py — rodar antes e depois de mexer aqui.
"""


def cras_dict(u):
    return {
        "id": u.id,
        "nome": u.nome,
        "codigo_cras": u.codigo_cras,
        "cnes": u.cnes,
        "endereco": u.endereco,
        "bairro": u.bairro,
        "municipio": u.municipio,
        "uf": u.uf,
        "cep": u.cep,
        "telefone": u.telefone,
        "email": u.email,
        "responsavel_tecnico": u.responsavel_tecnico,
        "ativo": u.ativo,
    }


def familia_dict(f):
    return {
        "id": f.id,
        "numero_prontuario": f.numero_prontuario,
        "responsavel_nome": f.responsavel_nome,
        "responsavel_cpf": f.responsavel_cpf,
        "responsavel_nis": f.responsavel_nis,
        "responsavel_cns": f.responsavel_cns,
        "responsavel_data_nascimento": str(f.responsavel_data_nascimento) if f.responsavel_data_nascimento else None,
        "responsavel_telefone": f.responsavel_telefone,
        "num_integrantes": f.num_integrantes,
        "renda_familiar_total": float(f.renda_familiar_total) if f.renda_familiar_total is not None else None,
        "endereco": f.endereco,
        "bairro": f.bairro,
        "cadUnico_numero_seq": f.cadUnico_numero_seq,
        "marcador_pbf": f.marcador_pbf,
        "marcador_bpc": f.marcador_bpc,
        "situacao": f.situacao,
        "unidade_cras_id": f.unidade_cras_id,
        "unidade_cras_nome": f.unidade_cras.nome if f.unidade_cras else None,
        "data_cadastro": str(f.data_cadastro),
        "observacoes": f.observacoes,
        "criado_em": f.criado_em.isoformat(),
    }


def visita_dict(v):
    return {
        "id": v.id,
        "familia_id": v.familia_id,
        "familia_nome": v.familia.responsavel_nome,
        "tecnico_nome": v.tecnico_nome,
        "data_visita": str(v.data_visita),
        "objetivo": v.objetivo,
        "relato": v.relato,
        "resultado": v.resultado,
        "vulnerabilidade_identificada": v.vulnerabilidade_identificada,
        "criado_em": v.criado_em.isoformat(),
    }
