"""
Treinamento interno / e-learning — cursos próprios da empresa, com matrícula,
conclusão e emissão de certificado (modelo visual + assinatura do treinador +
QR code de verificação).

Ao concluir um curso, um TreinamentoNR "de verdade" é criado (via
_criar_treinamento, compartilhado com o fluxo de registro manual/em lote),
então o treinamento interno aparece automaticamente na conformidade, no
relatório de homem-hora e no Assistente IA — sem duplicar lógica.
"""
import json
from datetime import date, timedelta

from django.http import FileResponse, Http404, HttpResponse, JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.csrf import csrf_exempt

from .models import (
    AssinaturaTreinador,
    ConfiguracaoMarca,
    CursoInterno,
    FuncionarioSST,
    MatriculaCursoInterno,
    ModeloCertificado,
    TipoTreinamentoNR,
)
from .views_sst import _criar_treinamento, _empresa_autenticada, _sst_nao_autorizado


# ── Assinaturas de treinador ───────────────────────────────────────────────────

@csrf_exempt
def api_assinaturas_treinador(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return _sst_nao_autorizado()

    if request.method == "GET":
        qs = AssinaturaTreinador.objects.filter(empresa=empresa, ativo=True).order_by("nome")
        return JsonResponse({"assinaturas": [
            {
                "id": a.id,
                "nome": a.nome,
                "cargo": a.cargo,
                "registro_profissional": a.registro_profissional,
                "tem_imagem": bool(a.imagem_assinatura),
            }
            for a in qs
        ]})

    if request.method == "POST":
        try:
            data = json.loads(request.body)
        except Exception:
            return JsonResponse({"erro": "JSON inválido"}, status=400)
        nome = (data.get("nome") or "").strip()
        if not nome:
            return JsonResponse({"erro": "Informe o nome do treinador"}, status=400)
        a = AssinaturaTreinador.objects.create(
            empresa=empresa,
            nome=nome,
            cargo=(data.get("cargo") or "").strip(),
            registro_profissional=(data.get("registro_profissional") or "").strip(),
        )
        return JsonResponse({"ok": True, "id": a.id})

    return JsonResponse({"erro": "método não permitido"}, status=405)


@csrf_exempt
def api_assinatura_treinador_detalhe(request, assinatura_id):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return _sst_nao_autorizado()
    try:
        a = AssinaturaTreinador.objects.get(id=assinatura_id, empresa=empresa)
    except AssinaturaTreinador.DoesNotExist:
        return JsonResponse({"erro": "Assinatura não encontrada"}, status=404)

    if request.method in ("PUT", "PATCH"):
        try:
            data = json.loads(request.body)
        except Exception:
            return JsonResponse({"erro": "JSON inválido"}, status=400)
        if "nome" in data:
            a.nome = (data.get("nome") or "").strip() or a.nome
        if "cargo" in data:
            a.cargo = (data.get("cargo") or "").strip()
        if "registro_profissional" in data:
            a.registro_profissional = (data.get("registro_profissional") or "").strip()
        if "ativo" in data:
            a.ativo = bool(data.get("ativo"))
        a.save()
        return JsonResponse({"ok": True})

    if request.method == "DELETE":
        a.ativo = False
        a.save(update_fields=["ativo"])
        return JsonResponse({"ok": True})

    return JsonResponse({"erro": "método não permitido"}, status=405)


def api_assinatura_treinador_arquivo(request, assinatura_id):
    """GET baixa a imagem da assinatura | POST (multipart, campo 'arquivo') envia."""
    empresa = _empresa_autenticada(request)
    if not empresa:
        return _sst_nao_autorizado()
    try:
        a = AssinaturaTreinador.objects.get(id=assinatura_id, empresa=empresa)
    except AssinaturaTreinador.DoesNotExist:
        return JsonResponse({"erro": "Assinatura não encontrada"}, status=404)

    if request.method == "GET":
        if not a.imagem_assinatura:
            raise Http404
        return FileResponse(a.imagem_assinatura.open("rb"), filename=f"assinatura_{a.id}.png")

    if request.method == "POST":
        arquivo = request.FILES.get("arquivo")
        if not arquivo:
            return JsonResponse({"erro": "Envie o arquivo no campo 'arquivo'"}, status=400)
        a.imagem_assinatura = arquivo
        a.save(update_fields=["imagem_assinatura"])
        return JsonResponse({"ok": True})

    return JsonResponse({"erro": "método não permitido"}, status=405)


# ── Modelos de certificado ──────────────────────────────────────────────────────

@csrf_exempt
def api_modelos_certificado(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return _sst_nao_autorizado()

    if request.method == "GET":
        qs = ModeloCertificado.objects.filter(empresa=empresa, ativo=True).order_by("-padrao", "nome")
        return JsonResponse({"modelos": [
            {
                "id": m.id,
                "nome": m.nome,
                "estilo": m.estilo,
                "estilo_label": m.get_estilo_display(),
                "cor_destaque": m.cor_destaque,
                "texto_rodape": m.texto_rodape,
                "padrao": m.padrao,
            }
            for m in qs
        ]})

    if request.method == "POST":
        try:
            data = json.loads(request.body)
        except Exception:
            return JsonResponse({"erro": "JSON inválido"}, status=400)
        nome = (data.get("nome") or "").strip()
        if not nome:
            return JsonResponse({"erro": "Informe o nome do modelo"}, status=400)
        estilo = data.get("estilo") or ModeloCertificado.ESTILO_CLASSICO
        if estilo not in dict(ModeloCertificado.ESTILOS):
            return JsonResponse({"erro": "Estilo inválido"}, status=400)
        padrao = bool(data.get("padrao"))
        if padrao:
            ModeloCertificado.objects.filter(empresa=empresa, padrao=True).update(padrao=False)
        m = ModeloCertificado.objects.create(
            empresa=empresa,
            nome=nome,
            estilo=estilo,
            cor_destaque=(data.get("cor_destaque") or "").strip(),
            texto_rodape=(data.get("texto_rodape") or "").strip(),
            padrao=padrao,
        )
        return JsonResponse({"ok": True, "id": m.id})

    return JsonResponse({"erro": "método não permitido"}, status=405)


@csrf_exempt
def api_modelo_certificado_detalhe(request, modelo_id):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return _sst_nao_autorizado()
    try:
        m = ModeloCertificado.objects.get(id=modelo_id, empresa=empresa)
    except ModeloCertificado.DoesNotExist:
        return JsonResponse({"erro": "Modelo não encontrado"}, status=404)

    if request.method in ("PUT", "PATCH"):
        try:
            data = json.loads(request.body)
        except Exception:
            return JsonResponse({"erro": "JSON inválido"}, status=400)
        if "nome" in data:
            m.nome = (data.get("nome") or "").strip() or m.nome
        if "estilo" in data and data["estilo"] in dict(ModeloCertificado.ESTILOS):
            m.estilo = data["estilo"]
        if "cor_destaque" in data:
            m.cor_destaque = (data.get("cor_destaque") or "").strip()
        if "texto_rodape" in data:
            m.texto_rodape = (data.get("texto_rodape") or "").strip()
        if "padrao" in data:
            padrao = bool(data.get("padrao"))
            if padrao:
                ModeloCertificado.objects.filter(empresa=empresa, padrao=True).exclude(id=m.id).update(padrao=False)
            m.padrao = padrao
        if "ativo" in data:
            m.ativo = bool(data.get("ativo"))
        m.save()
        return JsonResponse({"ok": True})

    if request.method == "DELETE":
        m.ativo = False
        m.save(update_fields=["ativo"])
        return JsonResponse({"ok": True})

    return JsonResponse({"erro": "método não permitido"}, status=405)


# ── Cursos internos ──────────────────────────────────────────────────────────────

def _curso_dict(c):
    total = c.matriculas.count()
    concluidas = c.matriculas.filter(status=MatriculaCursoInterno.STATUS_CONCLUIDO).count()
    return {
        "id": c.id,
        "titulo": c.titulo,
        "descricao": c.descricao,
        "video_url": c.video_url,
        "material_texto": c.material_texto,
        "tem_material_arquivo": bool(c.material_arquivo),
        "carga_horaria": c.carga_horaria,
        "tipo_treinamento_id": c.tipo_treinamento_id,
        "tipo_treinamento_nome": c.tipo_treinamento.nome if c.tipo_treinamento else None,
        "modelo_certificado_id": c.modelo_certificado_id,
        "assinatura_treinador_id": c.assinatura_treinador_id,
        "ativo": c.ativo,
        "total_matriculados": total,
        "total_concluidos": concluidas,
    }


@csrf_exempt
def api_cursos_internos(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return _sst_nao_autorizado()

    if request.method == "GET":
        qs = CursoInterno.objects.filter(empresa=empresa, ativo=True).select_related("tipo_treinamento").order_by("-criado_em")
        return JsonResponse({"cursos": [_curso_dict(c) for c in qs]})

    if request.method == "POST":
        try:
            data = json.loads(request.body)
        except Exception:
            return JsonResponse({"erro": "JSON inválido"}, status=400)
        titulo = (data.get("titulo") or "").strip()
        if not titulo:
            return JsonResponse({"erro": "Informe o título do curso"}, status=400)
        try:
            carga = int(data.get("carga_horaria") or 1)
        except (TypeError, ValueError):
            carga = 1

        tipo_treinamento = None
        if data.get("tipo_treinamento_id"):
            tipo_treinamento = TipoTreinamentoNR.objects.filter(id=data["tipo_treinamento_id"], empresa=empresa).first()
        modelo_certificado = None
        if data.get("modelo_certificado_id"):
            modelo_certificado = ModeloCertificado.objects.filter(id=data["modelo_certificado_id"], empresa=empresa).first()
        assinatura_treinador = None
        if data.get("assinatura_treinador_id"):
            assinatura_treinador = AssinaturaTreinador.objects.filter(id=data["assinatura_treinador_id"], empresa=empresa).first()

        c = CursoInterno.objects.create(
            empresa=empresa,
            titulo=titulo,
            descricao=(data.get("descricao") or "").strip(),
            video_url=(data.get("video_url") or "").strip(),
            material_texto=(data.get("material_texto") or "").strip(),
            carga_horaria=max(1, carga),
            tipo_treinamento=tipo_treinamento,
            modelo_certificado=modelo_certificado,
            assinatura_treinador=assinatura_treinador,
        )
        return JsonResponse({"ok": True, "id": c.id})

    return JsonResponse({"erro": "método não permitido"}, status=405)


@csrf_exempt
def api_curso_interno_detalhe(request, curso_id):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return _sst_nao_autorizado()
    try:
        c = CursoInterno.objects.get(id=curso_id, empresa=empresa)
    except CursoInterno.DoesNotExist:
        return JsonResponse({"erro": "Curso não encontrado"}, status=404)

    if request.method == "GET":
        return JsonResponse(_curso_dict(c))

    if request.method in ("PUT", "PATCH"):
        try:
            data = json.loads(request.body)
        except Exception:
            return JsonResponse({"erro": "JSON inválido"}, status=400)
        for campo in ("titulo", "descricao", "video_url", "material_texto"):
            if campo in data:
                setattr(c, campo, (data.get(campo) or "").strip())
        if "carga_horaria" in data:
            try:
                c.carga_horaria = max(1, int(data["carga_horaria"]))
            except (TypeError, ValueError):
                pass
        if "tipo_treinamento_id" in data:
            c.tipo_treinamento = TipoTreinamentoNR.objects.filter(id=data["tipo_treinamento_id"], empresa=empresa).first() if data["tipo_treinamento_id"] else None
        if "modelo_certificado_id" in data:
            c.modelo_certificado = ModeloCertificado.objects.filter(id=data["modelo_certificado_id"], empresa=empresa).first() if data["modelo_certificado_id"] else None
        if "assinatura_treinador_id" in data:
            c.assinatura_treinador = AssinaturaTreinador.objects.filter(id=data["assinatura_treinador_id"], empresa=empresa).first() if data["assinatura_treinador_id"] else None
        if "ativo" in data:
            c.ativo = bool(data.get("ativo"))
        c.save()
        return JsonResponse({"ok": True})

    if request.method == "DELETE":
        c.ativo = False
        c.save(update_fields=["ativo"])
        return JsonResponse({"ok": True})

    return JsonResponse({"erro": "método não permitido"}, status=405)


def api_curso_interno_material(request, curso_id):
    """GET baixa o material de apoio (PDF) | POST (multipart, campo 'arquivo') envia."""
    empresa = _empresa_autenticada(request)
    if not empresa:
        return _sst_nao_autorizado()
    try:
        c = CursoInterno.objects.get(id=curso_id, empresa=empresa)
    except CursoInterno.DoesNotExist:
        return JsonResponse({"erro": "Curso não encontrado"}, status=404)

    if request.method == "GET":
        if not c.material_arquivo:
            raise Http404
        return FileResponse(c.material_arquivo.open("rb"), filename=f"material_curso_{c.id}.pdf")

    if request.method == "POST":
        arquivo = request.FILES.get("arquivo")
        if not arquivo:
            return JsonResponse({"erro": "Envie o arquivo no campo 'arquivo'"}, status=400)
        c.material_arquivo = arquivo
        c.save(update_fields=["material_arquivo"])
        return JsonResponse({"ok": True})

    return JsonResponse({"erro": "método não permitido"}, status=405)


# ── Matrículas ────────────────────────────────────────────────────────────────

def _matricula_dict(m):
    return {
        "id": m.id,
        "funcionario_id": m.funcionario_id,
        "funcionario_nome": m.funcionario.nome,
        "status": m.status,
        "status_label": m.get_status_display(),
        "data_matricula": m.data_matricula.isoformat(),
        "data_conclusao": m.data_conclusao.isoformat() if m.data_conclusao else None,
        "numero_certificado": m.numero_certificado,
        "link_acesso": f"/curso-interno/{m.token_acesso}/",
    }


@csrf_exempt
def api_curso_interno_matricular(request, curso_id):
    """POST — matricula uma lista de funcionários (funcionario_ids) no curso."""
    empresa = _empresa_autenticada(request)
    if not empresa:
        return _sst_nao_autorizado()
    try:
        curso = CursoInterno.objects.get(id=curso_id, empresa=empresa, ativo=True)
    except CursoInterno.DoesNotExist:
        return JsonResponse({"erro": "Curso não encontrado"}, status=404)
    if request.method != "POST":
        return JsonResponse({"erro": "método não permitido"}, status=405)

    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({"erro": "JSON inválido"}, status=400)
    funcionario_ids = data.get("funcionario_ids") or []
    if not funcionario_ids:
        return JsonResponse({"erro": "Selecione ao menos um funcionário"}, status=400)

    criadas, ja_matriculados = [], []
    for func in FuncionarioSST.objects.filter(id__in=funcionario_ids, empresa=empresa, ativo=True):
        matricula, criada = MatriculaCursoInterno.objects.get_or_create(
            curso=curso, funcionario=func, empresa=empresa,
        )
        (criadas if criada else ja_matriculados).append(matricula.id)

    return JsonResponse({"ok": True, "matriculados": len(criadas), "ja_matriculados": len(ja_matriculados)})


def api_curso_interno_matriculas(request, curso_id):
    """GET — lista as matrículas de um curso, com status e link de acesso."""
    empresa = _empresa_autenticada(request)
    if not empresa:
        return _sst_nao_autorizado()
    try:
        curso = CursoInterno.objects.get(id=curso_id, empresa=empresa)
    except CursoInterno.DoesNotExist:
        return JsonResponse({"erro": "Curso não encontrado"}, status=404)
    qs = curso.matriculas.select_related("funcionario").order_by("funcionario__nome")
    return JsonResponse({"matriculas": [_matricula_dict(m) for m in qs]})


@csrf_exempt
def api_matricula_concluir_manual(request, matricula_id):
    """POST — gestor marca a matrícula como concluída manualmente (ex: turma presencial),
    sem passar pela página pública do funcionário."""
    empresa = _empresa_autenticada(request)
    if not empresa:
        return _sst_nao_autorizado()
    try:
        matricula = MatriculaCursoInterno.objects.select_related("curso", "funcionario").get(id=matricula_id, empresa=empresa)
    except MatriculaCursoInterno.DoesNotExist:
        return JsonResponse({"erro": "Matrícula não encontrada"}, status=404)
    if request.method != "POST":
        return JsonResponse({"erro": "método não permitido"}, status=405)
    if matricula.status == MatriculaCursoInterno.STATUS_CONCLUIDO:
        return JsonResponse({"erro": "Matrícula já concluída"}, status=400)

    _concluir_matricula(matricula)
    return JsonResponse({"ok": True, "numero_certificado": matricula.numero_certificado})


def _concluir_matricula(matricula):
    """Marca a matrícula como concluída, cria o TreinamentoNR de conformidade
    correspondente e gera o número do certificado. Compartilhado entre a
    conclusão manual (gestor) e a conclusão pela página pública (funcionário)."""
    curso = matricula.curso
    empresa = matricula.empresa
    hoje = date.today()

    data_validade = None
    if curso.tipo_treinamento and curso.tipo_treinamento.periodicidade_dias:
        data_validade = hoje + timedelta(days=curso.tipo_treinamento.periodicidade_dias)

    treinamento = _criar_treinamento(empresa, matricula.funcionario, {
        "tipo_treinamento_id": curso.tipo_treinamento_id,
        "titulo": curso.titulo,
        "instrutor": curso.assinatura_treinador.nome if curso.assinatura_treinador else "",
        "carga_horaria": curso.carga_horaria,
        "data_realizacao": hoje.isoformat(),
        "data_validade": data_validade.isoformat() if data_validade else "",
        "certificado": f"CURSO-INTERNO-{matricula.id}",
    })

    from django.utils import timezone
    matricula.status = MatriculaCursoInterno.STATUS_CONCLUIDO
    matricula.data_conclusao = timezone.now()
    matricula.treinamento_nr = treinamento
    matricula.numero_certificado = f"SST-{hoje.year}-{matricula.id:06d}"
    matricula.save(update_fields=["status", "data_conclusao", "treinamento_nr", "numero_certificado"])
    return matricula


def _dados_certificado(matricula, request):
    """Monta o dict que gerar_certificado_treinamento() espera, a partir da matrícula."""
    curso = matricula.curso
    empresa = matricula.empresa
    modelo = curso.modelo_certificado or ModeloCertificado.objects.filter(empresa=empresa, padrao=True, ativo=True).first()
    assinatura = curso.assinatura_treinador

    marca = ConfiguracaoMarca.objects.filter(empresa=empresa).first()
    logo_url = marca.logo_url if marca else ""

    scheme = "https" if request.is_secure() else "http"
    host = request.get_host()
    url_verificacao = f"{scheme}://{host}/certificado/verificar/{matricula.numero_certificado}/"

    return {
        "funcionario_nome": matricula.funcionario.nome,
        "funcionario_cpf": matricula.funcionario.cpf,
        "curso_titulo": curso.titulo,
        "carga_horaria": curso.carga_horaria,
        "data_conclusao": matricula.data_conclusao.strftime("%d/%m/%Y") if matricula.data_conclusao else "",
        "treinador_nome": assinatura.nome if assinatura else "",
        "treinador_cargo": assinatura.cargo if assinatura else "",
        "treinador_registro": assinatura.registro_profissional if assinatura else "",
        "treinador_assinatura_path": assinatura.imagem_assinatura.path if (assinatura and assinatura.imagem_assinatura) else None,
        "empresa_nome": empresa.nome,
        "empresa_logo_url": logo_url,
        "estilo": modelo.estilo if modelo else ModeloCertificado.ESTILO_CLASSICO,
        "cor_destaque": modelo.cor_destaque if modelo else "",
        "texto_rodape": modelo.texto_rodape if modelo else "",
        "numero_certificado": matricula.numero_certificado,
        "url_verificacao": url_verificacao,
    }


def api_matricula_certificado_pdf(request, matricula_id):
    """GET — baixa/visualiza o certificado em PDF de uma matrícula concluída."""
    empresa = _empresa_autenticada(request)
    if not empresa:
        return _sst_nao_autorizado()
    try:
        matricula = MatriculaCursoInterno.objects.select_related(
            "curso", "curso__modelo_certificado", "curso__assinatura_treinador", "funcionario",
        ).get(id=matricula_id, empresa=empresa)
    except MatriculaCursoInterno.DoesNotExist:
        return JsonResponse({"erro": "Matrícula não encontrada"}, status=404)
    if matricula.status != MatriculaCursoInterno.STATUS_CONCLUIDO:
        return JsonResponse({"erro": "Curso ainda não concluído"}, status=400)

    from .pdf_sst import gerar_certificado_treinamento
    pdf_bytes = gerar_certificado_treinamento(_dados_certificado(matricula, request))
    resp = HttpResponse(pdf_bytes, content_type="application/pdf")
    disposition = "attachment" if request.GET.get("download") else "inline"
    resp["Content-Disposition"] = f'{disposition}; filename="certificado_{matricula.numero_certificado}.pdf"'
    return resp


@csrf_exempt
def api_matricula_certificado_email(request, matricula_id):
    """POST — envia o certificado por e-mail (do funcionário ou de quem for informado)."""
    empresa = _empresa_autenticada(request)
    if not empresa:
        return _sst_nao_autorizado()
    if request.method != "POST":
        return JsonResponse({"erro": "método não permitido"}, status=405)
    try:
        matricula = MatriculaCursoInterno.objects.select_related(
            "curso", "curso__modelo_certificado", "curso__assinatura_treinador", "funcionario",
        ).get(id=matricula_id, empresa=empresa)
    except MatriculaCursoInterno.DoesNotExist:
        return JsonResponse({"erro": "Matrícula não encontrada"}, status=404)
    if matricula.status != MatriculaCursoInterno.STATUS_CONCLUIDO:
        return JsonResponse({"erro": "Curso ainda não concluído"}, status=400)

    try:
        data = json.loads(request.body or "{}")
    except Exception:
        data = {}
    destinatario = (data.get("email") or "").strip()
    if not destinatario or "@" not in destinatario:
        return JsonResponse({"erro": "Informe um e-mail válido"}, status=400)

    from .pdf_sst import gerar_certificado_treinamento
    pdf_bytes = gerar_certificado_treinamento(_dados_certificado(matricula, request))

    from django.core.mail import EmailMessage
    try:
        msg = EmailMessage(
            subject=f"[SoloCRT] Certificado — {matricula.curso.titulo}",
            body=(
                f"Segue em anexo o certificado de conclusão do curso {matricula.curso.titulo} "
                f"para {matricula.funcionario.nome}.\n\n-- \nSoloCRT · Sistema de Gestão SST"
            ),
            from_email=None,
            to=[destinatario],
        )
        msg.attach(f"certificado_{matricula.numero_certificado}.pdf", pdf_bytes, "application/pdf")
        enviados = msg.send(fail_silently=False)
        if enviados < 1:
            return JsonResponse({"erro": "Servidor de e-mail não confirmou o envio."}, status=502)
    except Exception as exc:
        import logging
        logging.getLogger(__name__).error("Erro ao enviar certificado por e-mail: %s", exc)
        return JsonResponse({"erro": f"Falha ao enviar e-mail: {exc}"}, status=502)

    return JsonResponse({"ok": True})


# ── Página administrativa (gestor) ───────────────────────────────────────────────

def sst_curso_interno_page(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return redirect("/login-empresa/")
    return render(request, "sst_curso_interno.html", {"empresa_nome": empresa.nome})


# ── Página pública do funcionário (sem login, via token) ──────────────────────

def curso_interno_publico_page(request, token):
    try:
        matricula = MatriculaCursoInterno.objects.select_related("curso", "funcionario", "empresa").get(token_acesso=token)
    except MatriculaCursoInterno.DoesNotExist:
        raise Http404
    return render(request, "curso_interno_publico.html", {
        "matricula": matricula,
        "curso": matricula.curso,
        "empresa_nome": matricula.empresa.nome,
        "token": token,
    })


def api_curso_interno_publico_material(request, token):
    """GET — serve o material de apoio (PDF) sem exigir login, validado pelo token da matrícula."""
    try:
        matricula = MatriculaCursoInterno.objects.select_related("curso").get(token_acesso=token)
    except MatriculaCursoInterno.DoesNotExist:
        raise Http404
    if not matricula.curso.material_arquivo:
        raise Http404
    return FileResponse(matricula.curso.material_arquivo.open("rb"), filename=f"material_{matricula.curso.id}.pdf")


@csrf_exempt
def api_curso_interno_publico_concluir(request, token):
    """POST — o funcionário marca o curso como concluído a partir da página pública."""
    try:
        matricula = MatriculaCursoInterno.objects.select_related("curso", "funcionario", "empresa").get(token_acesso=token)
    except MatriculaCursoInterno.DoesNotExist:
        raise Http404
    if request.method != "POST":
        return JsonResponse({"erro": "método não permitido"}, status=405)
    if matricula.status == MatriculaCursoInterno.STATUS_CONCLUIDO:
        return JsonResponse({"ok": True, "ja_concluido": True, "numero_certificado": matricula.numero_certificado})

    _concluir_matricula(matricula)
    return JsonResponse({"ok": True, "numero_certificado": matricula.numero_certificado})


def api_curso_interno_publico_certificado_pdf(request, token):
    """GET — o funcionário baixa/visualiza o próprio certificado a partir da página pública."""
    try:
        matricula = MatriculaCursoInterno.objects.select_related(
            "curso", "curso__modelo_certificado", "curso__assinatura_treinador", "funcionario", "empresa",
        ).get(token_acesso=token)
    except MatriculaCursoInterno.DoesNotExist:
        raise Http404
    if matricula.status != MatriculaCursoInterno.STATUS_CONCLUIDO:
        return JsonResponse({"erro": "Curso ainda não concluído"}, status=400)

    from .pdf_sst import gerar_certificado_treinamento
    pdf_bytes = gerar_certificado_treinamento(_dados_certificado(matricula, request))
    resp = HttpResponse(pdf_bytes, content_type="application/pdf")
    disposition = "attachment" if request.GET.get("download") else "inline"
    resp["Content-Disposition"] = f'{disposition}; filename="certificado_{matricula.numero_certificado}.pdf"'
    return resp


# ── Verificação pública do certificado (via QR code) ──────────────────────────

def certificado_verificar_page(request, numero_certificado):
    matricula = MatriculaCursoInterno.objects.select_related("curso", "funcionario", "empresa").filter(
        numero_certificado=numero_certificado, status=MatriculaCursoInterno.STATUS_CONCLUIDO,
    ).first()
    return render(request, "certificado_verificar.html", {
        "valido": bool(matricula),
        "matricula": matricula,
        "numero_certificado": numero_certificado,
    })
