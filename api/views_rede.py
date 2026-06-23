import json
from datetime import date, datetime
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.db.models import F, Q, Sum
from .models import (
    Empresa, Rede, UnidadeRede, TransferenciaEstoque, MensagemRede,
    PlanoSaude, BeneficiarioPlano, GuiaAutorizacao, ItemFarmacia,
    CarenciaBeneficiario,
)
from .access_control import get_setor


def get_empresa(request):
    empresa = getattr(request, 'empresa', None)
    if empresa:
        return empresa
    # Fallback: try auth_token cookie
    from django.conf import settings
    import jwt as pyjwt
    token = request.COOKIES.get('auth_token')
    if not token:
        return None
    try:
        payload = pyjwt.decode(token, settings.JWT_SECRET_KEY, algorithms=['HS256'])
        from .models import Empresa
        return Empresa.objects.filter(id=payload.get('empresa_id')).first()
    except Exception:
        return None


def get_unidade(empresa):
    """Get or create UnidadeRede for this empresa."""
    try:
        return UnidadeRede.objects.get(empresa=empresa)
    except UnidadeRede.DoesNotExist:
        return None


def _parse_date_or_none(value):
    if not value:
        return None
    if isinstance(value, date):
        return value
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, str):
        for fmt in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f"):
            try:
                return datetime.strptime(value, fmt).date()
            except ValueError:
                continue
    return None


def _verificar_acesso_rede(request):
    """
    Verifica se o tenant tem acesso à funcionalidade multi-unidade.
    - Setor 'farmacia': exige feature 'farmacia.multi_unidade' (plano Rede Regional)
    - Setor 'rede': exige feature 'rede.multi_unidade' (qualquer plano de rede)
    - Outros setores: bloqueado (rede é exclusiva para farmácia e setor rede)
    Retorna (empresa, None) se OK, ou (None, JsonResponse) com erro.
    """
    from .access_control import empresa_tem_feature
    from .planos import detalhes_pacote

    empresa = get_empresa(request)
    if not empresa:
        return None, JsonResponse({"erro": "Não autenticado"}, status=401)

    setor = get_setor(empresa)

    if setor == "farmacia":
        if not empresa_tem_feature(empresa, "farmacia.multi_unidade"):
            pacote = detalhes_pacote(empresa.pacote_codigo)
            return None, JsonResponse({
                "erro": "Rede multi-unidade disponível apenas no plano Rede Farmacêutica Regional.",
                "feature_requerida": "farmacia.multi_unidade",
                "plano_atual": pacote.get("label", ""),
                "upgrade_necessario": True,
            }, status=403)
        return empresa, None

    if setor == "rede":
        if not empresa_tem_feature(empresa, "rede.multi_unidade"):
            return None, JsonResponse({
                "erro": "Acesso à rede não disponível no seu plano.",
                "feature_requerida": "rede.multi_unidade",
                "upgrade_necessario": True,
            }, status=403)
        return empresa, None

    if setor == "hospital":
        if not empresa_tem_feature(empresa, "hospital.multi_unidade"):
            pacote = detalhes_pacote(empresa.pacote_codigo)
            return None, JsonResponse({
                "erro": "Rede multi-unidade disponível apenas no plano Rede Hospitalar.",
                "feature_requerida": "hospital.multi_unidade",
                "plano_atual": pacote.get("label", ""),
                "upgrade_necessario": True,
            }, status=403)
        return empresa, None

    # Outros setores não têm acesso à funcionalidade de rede
    return None, JsonResponse(
        {"erro": f"Módulo de rede não disponível para o setor '{setor}'."},
        status=403,
    )


def _rede_dentro_do_limite(rede):
    """
    Verifica se a rede ainda tem espaço para mais uma unidade, usando o limite
    de max_unidades do plano da unidade fundadora (primeira a entrar na rede).
    """
    from .access_control import dentro_do_limite
    primeira = rede.unidades.filter(ativa=True).order_by("criada_em").first()
    if not primeira:
        return True
    contagem_atual = rede.unidades.filter(ativa=True).count()
    return dentro_do_limite(primeira.empresa, "max_unidades", contagem_atual)


# ─── REDE ────────────────────────────────────────────────────────────────────

@csrf_exempt
def api_redes(request):
    empresa, err = _verificar_acesso_rede(request)
    if err:
        return err

    if request.method == 'GET':
        unidade = get_unidade(empresa)
        if unidade and unidade.rede:
            rede = unidade.rede
            unidades = list(rede.unidades.filter(ativa=True).values(
                'id', 'nome_unidade', 'codigo_unidade', 'cidade', 'estado',
                'responsavel', 'telefone', 'tipo', 'empresa__id', 'empresa__nome'
            ))
            return JsonResponse({
                'rede': {
                    'id': rede.id,
                    'nome': rede.nome,
                    'tipo': rede.tipo,
                    'cnpj_raiz': rede.cnpj_raiz,
                    'total_unidades': len(unidades),
                },
                'unidades': unidades,
                'minha_unidade_id': unidade.id,
            })
        # Standalone — not in a network
        return JsonResponse({'rede': None, 'unidades': [], 'minha_unidade_id': None})

    if request.method == 'POST':
        data = json.loads(request.body)
        rede = Rede.objects.create(
            nome=data.get('nome', ''),
            tipo=data.get('tipo', 'farmacia'),
            cnpj_raiz=data.get('cnpj_raiz', ''),
            descricao=data.get('descricao', ''),
        )
        # Register current empresa as first unit
        unidade, _ = UnidadeRede.objects.get_or_create(empresa=empresa)
        unidade.rede = rede
        unidade.tipo = data.get('tipo_unidade', 'farmacia')
        unidade.nome_unidade = data.get('nome_unidade', empresa.nome)
        unidade.codigo_unidade = data.get('codigo_unidade', 'UN-001')
        unidade.save()
        return JsonResponse({'ok': True, 'rede_id': rede.id})

    return JsonResponse({'erro': 'Método não permitido'}, status=405)


@csrf_exempt
def api_rede_convidar(request):
    """Generate invite code or register a unit into the network."""
    import secrets
    empresa, err = _verificar_acesso_rede(request)
    if err:
        return err

    unidade = get_unidade(empresa)
    if not unidade or not unidade.rede:
        return JsonResponse({'erro': 'Você não pertence a uma rede'}, status=400)

    if request.method == 'POST':
        data = json.loads(request.body)
        rede = unidade.rede

        # Ensure the rede has an invite code
        if not rede.codigo_convite:
            rede.codigo_convite = 'RD-' + secrets.token_urlsafe(8).upper()[:10]
            rede.save()

        email_destino = data.get('email_empresa', '').strip()
        if email_destino:
            # Register another empresa by email into the same network
            try:
                empresa_destino = Empresa.objects.get(email=email_destino)
            except Empresa.DoesNotExist:
                # Don't reveal if email exists — return invite code instead
                return JsonResponse({
                    'ok': True,
                    'codigo_convite': rede.codigo_convite,
                    'aviso': 'Empresa não encontrada no sistema. Compartilhe o código do convite diretamente.'
                })
            ja_e_membro = UnidadeRede.objects.filter(empresa=empresa_destino, rede=rede, ativa=True).exists()
            if not ja_e_membro and not _rede_dentro_do_limite(rede):
                return JsonResponse({
                    'erro': 'Limite de unidades do plano atingido. Faça upgrade para adicionar mais unidades.',
                    'upgrade_necessario': True,
                }, status=403)
            u, created = UnidadeRede.objects.get_or_create(empresa=empresa_destino)
            u.rede = rede
            u.tipo = data.get('tipo', 'farmacia')
            u.nome_unidade = data.get('nome_unidade', empresa_destino.nome)
            u.codigo_unidade = data.get('codigo_unidade', '')
            u.save()
            return JsonResponse({'ok': True, 'criada': created, 'unidade_id': u.id, 'codigo_convite': rede.codigo_convite})
        else:
            # Just return invite code
            return JsonResponse({'ok': True, 'codigo_convite': rede.codigo_convite})

    return JsonResponse({'erro': 'Método não permitido'}, status=405)


@csrf_exempt
def api_rede_entrar(request):
    """POST /api/rede/entrar/ — join a rede using an invite code."""
    if request.method != 'POST':
        return JsonResponse({'erro': 'Método não permitido'}, status=405)
    empresa, err = _verificar_acesso_rede(request)
    if err:
        return err
    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({'erro': 'JSON inválido'}, status=400)
    codigo = (data.get('codigo_convite') or '').strip().upper()
    if not codigo:
        return JsonResponse({'erro': 'Código do convite é obrigatório'}, status=400)
    try:
        rede = Rede.objects.get(codigo_convite=codigo, ativa=True)
    except Rede.DoesNotExist:
        return JsonResponse({'erro': 'Código de convite inválido ou rede não encontrada'}, status=404)

    u, created = UnidadeRede.objects.get_or_create(empresa=empresa)
    if u.rede and u.rede != rede:
        return JsonResponse({'erro': 'Você já pertence a outra rede'}, status=400)
    ja_e_membro = u.rede == rede
    if not ja_e_membro and not _rede_dentro_do_limite(rede):
        return JsonResponse({
            'erro': 'Limite de unidades do plano atingido nesta rede. Peça à unidade fundadora um upgrade de plano.',
            'upgrade_necessario': True,
        }, status=403)
    u.rede = rede
    u.nome_unidade = data.get('nome_unidade', empresa.nome) or empresa.nome
    u.codigo_unidade = data.get('codigo_unidade', '')
    u.save()
    return JsonResponse({'ok': True, 'id': u.id, 'rede_nome': rede.nome})


# ─── ESTOQUE CONSOLIDADO DA REDE ─────────────────────────────────────────────

def api_rede_estoque(request):
    empresa, err = _verificar_acesso_rede(request)
    if err:
        return err

    unidade = get_unidade(empresa)
    if not unidade or not unidade.rede:
        return JsonResponse({'unidades': [], 'aviso': 'Não pertence a uma rede'})

    rede = unidade.rede
    unidades_rede = rede.unidades.filter(ativa=True)

    resultado = []
    for u in unidades_rede:
        itens = ItemFarmacia.objects.filter(empresa=u.empresa, ativo=True).values(
            'id', 'nome', 'categoria', 'estoque_atual', 'estoque_minimo', 'unidade_medida'
        )
        resultado.append({
            'unidade_id': u.id,
            'unidade_nome': u.nome_unidade or u.empresa.nome,
            'codigo': u.codigo_unidade,
            'cidade': u.cidade,
            'estado': u.estado,
            'eh_minha': u.empresa_id == empresa.id,
            'itens': list(itens),
            'total_itens': len(itens),
            'itens_criticos': sum(1 for i in itens if i['estoque_atual'] < i['estoque_minimo']),
        })

    return JsonResponse({'rede': rede.nome, 'unidades': resultado})


def api_rede_item_disponibilidade(request, nome_item):
    """Check availability of an item across all network units."""
    empresa, err = _verificar_acesso_rede(request)
    if err:
        return err

    unidade = get_unidade(empresa)
    if not unidade or not unidade.rede:
        return JsonResponse({'disponibilidade': []})

    rede = unidade.rede
    unidades_rede = rede.unidades.filter(ativa=True).exclude(empresa=empresa)

    disponibilidade = []
    for u in unidades_rede:
        itens = ItemFarmacia.objects.filter(
            empresa=u.empresa, ativo=True,
            nome__icontains=nome_item, estoque_atual__gt=0
        ).values('id', 'nome', 'estoque_atual', 'unidade_medida', 'estoque_minimo')
        if itens:
            disponibilidade.append({
                'unidade_id': u.id,
                'unidade_nome': u.nome_unidade or u.empresa.nome,
                'cidade': u.cidade,
                'estado': u.estado,
                'itens': list(itens),
            })

    return JsonResponse({'item': nome_item, 'disponibilidade': disponibilidade})


# ─── KPIS HOSPITALARES CONSOLIDADOS DA REDE ──────────────────────────────────

def api_rede_hospital_kpis(request):
    """Painel executivo consolidado + benchmarking entre unidades hospitalares da rede."""
    from datetime import date
    from .models import LeitoHospitalar, PacienteInternado, TriagemManchester
    from .access_control import empresa_tem_feature

    empresa, err = _verificar_acesso_rede(request)
    if err:
        return err

    setor = get_setor(empresa)
    feature_consolidado = "hospital.painel_executivo" if setor == "hospital" else "rede.kpis_consolidados"
    feature_benchmark = "hospital.benchmarking" if setor == "hospital" else "rede.benchmarking"
    if not empresa_tem_feature(empresa, feature_consolidado) and not empresa_tem_feature(empresa, feature_benchmark):
        return JsonResponse({
            "erro": "Funcionalidade não disponível no seu plano atual.",
            "feature_requerida": feature_consolidado,
            "upgrade_necessario": True,
        }, status=403)

    unidade = get_unidade(empresa)
    if not unidade or not unidade.rede:
        return JsonResponse({'rede': None, 'unidades': [], 'consolidado': None})

    rede = unidade.rede
    unidades_rede = rede.unidades.filter(ativa=True)
    hoje = date.today()

    unidades_kpis = []
    tot_leitos = tot_ocupados = tot_internados = tot_triagens = 0

    for u in unidades_rede:
        emp = u.empresa
        total_leitos = LeitoHospitalar.objects.filter(empresa=emp).count()
        leitos_ocupados = LeitoHospitalar.objects.filter(empresa=emp, status="ocupado").count()
        taxa_ocupacao_pct = round(leitos_ocupados / total_leitos * 100, 1) if total_leitos else 0.0
        pacientes_internados = PacienteInternado.objects.filter(empresa=emp, status="internado").count()
        triagens_hoje = TriagemManchester.objects.filter(empresa=emp, data_hora__date=hoje).count()
        triagens_vermelhas = TriagemManchester.objects.filter(
            empresa=emp, nivel="vermelho", status__in=["aguardando", "em_atendimento"]
        ).count()

        tot_leitos += total_leitos
        tot_ocupados += leitos_ocupados
        tot_internados += pacientes_internados
        tot_triagens += triagens_hoje

        unidades_kpis.append({
            'unidade_id': u.id,
            'unidade_nome': u.nome_unidade or emp.nome,
            'codigo': u.codigo_unidade,
            'cidade': u.cidade,
            'estado': u.estado,
            'eh_minha': emp.id == empresa.id,
            'total_leitos': total_leitos,
            'leitos_ocupados': leitos_ocupados,
            'taxa_ocupacao_pct': taxa_ocupacao_pct,
            'pacientes_internados': pacientes_internados,
            'triagens_hoje': triagens_hoje,
            'triagens_vermelhas_pendentes': triagens_vermelhas,
        })

    consolidado = {
        'total_unidades': len(unidades_kpis),
        'total_leitos': tot_leitos,
        'total_ocupados': tot_ocupados,
        'taxa_ocupacao_media_pct': round(tot_ocupados / tot_leitos * 100, 1) if tot_leitos else 0.0,
        'total_internados': tot_internados,
        'total_triagens_hoje': tot_triagens,
    }

    return JsonResponse({
        'rede': rede.nome,
        'unidades': unidades_kpis if empresa_tem_feature(empresa, feature_benchmark) else [],
        'consolidado': consolidado if empresa_tem_feature(empresa, feature_consolidado) else None,
    })


# ─── TRANSFERÊNCIAS ───────────────────────────────────────────────────────────

@csrf_exempt
def api_transferencias(request):
    empresa, err = _verificar_acesso_rede(request)
    if err:
        return err

    unidade = get_unidade(empresa)
    if not unidade:
        return JsonResponse({'erro': 'Unidade não configurada'}, status=400)

    if request.method == 'GET':
        filtro = request.GET.get('filtro', 'todas')  # todas, recebidas, enviadas, pendentes
        qs = TransferenciaEstoque.objects.filter(
            Q(unidade_solicitante=unidade) | Q(unidade_fornecedora=unidade)
        ).select_related('unidade_solicitante', 'unidade_fornecedora', 'item_farmacia')

        if filtro == 'recebidas':
            qs = qs.filter(unidade_fornecedora=unidade)
        elif filtro == 'enviadas':
            qs = qs.filter(unidade_solicitante=unidade)
        elif filtro == 'pendentes':
            qs = qs.filter(status='pendente')

        result = []
        for t in qs:
            result.append({
                'id': t.id,
                'nome_item': t.nome_item or (t.item_farmacia.nome if t.item_farmacia else '—'),
                'quantidade_solicitada': float(t.quantidade_solicitada),
                'quantidade_aprovada': float(t.quantidade_aprovada) if t.quantidade_aprovada else None,
                'status': t.status,
                'urgente': t.urgente,
                'motivo': t.motivo,
                'solicitante': t.unidade_solicitante.nome_unidade or str(t.unidade_solicitante),
                'fornecedora': t.unidade_fornecedora.nome_unidade or str(t.unidade_fornecedora),
                'sou_solicitante': t.unidade_solicitante_id == unidade.id,
                'sou_fornecedor': t.unidade_fornecedora_id == unidade.id,
                'solicitado_por': t.solicitado_por,
                'aprovado_por': t.aprovado_por,
                'solicitado_em': t.solicitado_em.isoformat(),
                'atualizado_em': t.atualizado_em.isoformat(),
            })

        pendentes_para_mim = qs.filter(unidade_fornecedora=unidade, status='pendente').count()
        return JsonResponse({'transferencias': result, 'pendentes_para_mim': pendentes_para_mim})

    if request.method == 'POST':
        data = json.loads(request.body)
        if not unidade.rede:
            return JsonResponse({'erro': 'Não pertence a uma rede'}, status=400)

        try:
            unidade_dest = UnidadeRede.objects.get(id=data['unidade_fornecedora_id'], rede=unidade.rede)
        except UnidadeRede.DoesNotExist:
            return JsonResponse({'erro': 'Unidade fornecedora não encontrada na rede'}, status=404)

        item_id = data.get('item_id')
        item = None
        nome_item = data.get('nome_item', '')
        if item_id:
            try:
                item = ItemFarmacia.objects.get(id=item_id, empresa=empresa)
                nome_item = item.nome
            except ItemFarmacia.DoesNotExist:
                pass

        t = TransferenciaEstoque.objects.create(
            rede=unidade.rede,
            unidade_solicitante=unidade,
            unidade_fornecedora=unidade_dest,
            item_farmacia=item,
            nome_item=nome_item,
            quantidade_solicitada=data.get('quantidade', 1),
            motivo=data.get('motivo', ''),
            observacoes=data.get('observacoes', ''),
            urgente=data.get('urgente', False),
            solicitado_por=data.get('solicitado_por', ''),
        )
        # Auto-create notification message
        MensagemRede.objects.create(
            rede=unidade.rede,
            remetente=unidade,
            destinatario=unidade_dest,
            tipo='transferencia',
            assunto=f'Solicitação de transferência — {nome_item}',
            corpo=f'{unidade.nome_unidade or unidade.empresa.nome} solicita {t.quantidade_solicitada} un de {nome_item}. Motivo: {t.motivo or "não informado"}',
            transferencia=t,
        )
        return JsonResponse({'ok': True, 'id': t.id})

    return JsonResponse({'erro': 'Método não permitido'}, status=405)


@csrf_exempt
def api_transferencia_detalhe(request, transferencia_id):
    empresa = get_empresa(request)
    if not empresa:
        return JsonResponse({'erro': 'Não autenticado'}, status=401)

    unidade = get_unidade(empresa)
    try:
        t = TransferenciaEstoque.objects.get(
            id=transferencia_id,
        )
    except TransferenciaEstoque.DoesNotExist:
        return JsonResponse({'erro': 'Não encontrada'}, status=404)

    if request.method == 'PUT':
        data = json.loads(request.body)
        novo_status = data.get('status')
        if novo_status:
            t.status = novo_status
        if 'quantidade_aprovada' in data:
            t.quantidade_aprovada = data['quantidade_aprovada']
        if 'aprovado_por' in data:
            t.aprovado_por = data['aprovado_por']
        t.save()

        # Notification message
        if novo_status in ('aprovada', 'enviada', 'recebida', 'cancelada'):
            label = {'aprovada': 'aprovada', 'enviada': 'enviada', 'recebida': 'recebida', 'cancelada': 'cancelada'}.get(novo_status, novo_status)
            MensagemRede.objects.create(
                rede=t.rede,
                remetente=unidade,
                destinatario=t.unidade_solicitante if unidade == t.unidade_fornecedora else t.unidade_fornecedora,
                tipo='transferencia',
                assunto=f'Transferência {label} — {t.nome_item}',
                corpo=f'A transferência de {t.quantidade_solicitada} un de {t.nome_item} foi {label}.',
                transferencia=t,
            )
        return JsonResponse({'ok': True})

    return JsonResponse({'erro': 'Método não permitido'}, status=405)


# ─── MENSAGENS ────────────────────────────────────────────────────────────────

@csrf_exempt
def api_mensagens_rede(request):
    empresa = get_empresa(request)
    if not empresa:
        return JsonResponse({'erro': 'Não autenticado'}, status=401)

    unidade = get_unidade(empresa)
    if not unidade or not unidade.rede:
        return JsonResponse({'mensagens': [], 'nao_lidas': 0})

    if request.method == 'GET':
        qs = MensagemRede.objects.filter(
            rede=unidade.rede
        ).filter(
            Q(destinatario=unidade) | Q(destinatario__isnull=True) | Q(remetente=unidade)
        ).select_related('remetente', 'destinatario', 'transferencia').order_by('-enviada_em')[:100]

        msgs = []
        for m in qs:
            msgs.append({
                'id': m.id,
                'tipo': m.tipo,
                'assunto': m.assunto,
                'corpo': m.corpo,
                'remetente': m.remetente.nome_unidade or str(m.remetente),
                'remetente_id': m.remetente_id,
                'destinatario': m.destinatario.nome_unidade if m.destinatario else 'Todos',
                'destinatario_id': m.destinatario_id,
                'lida': m.lida,
                'transferencia_id': m.transferencia_id,
                'sou_remetente': m.remetente_id == unidade.id,
                'enviada_em': m.enviada_em.isoformat(),
            })

        nao_lidas = MensagemRede.objects.filter(
            rede=unidade.rede,
            destinatario=unidade,
            lida=False
        ).count()

        return JsonResponse({'mensagens': msgs, 'nao_lidas': nao_lidas})

    if request.method == 'POST':
        data = json.loads(request.body)
        dest_id = data.get('destinatario_id')
        dest = None
        if dest_id:
            try:
                dest = UnidadeRede.objects.get(id=dest_id, rede=unidade.rede)
            except UnidadeRede.DoesNotExist:
                pass

        m = MensagemRede.objects.create(
            rede=unidade.rede,
            remetente=unidade,
            destinatario=dest,
            tipo=data.get('tipo', 'geral'),
            assunto=data.get('assunto', ''),
            corpo=data.get('corpo', ''),
        )
        return JsonResponse({'ok': True, 'id': m.id})

    return JsonResponse({'erro': 'Método não permitido'}, status=405)


@csrf_exempt
def api_mensagem_marcar_lida(request, msg_id):
    empresa = get_empresa(request)
    if not empresa:
        return JsonResponse({'erro': 'Não autenticado'}, status=401)

    if request.method == 'PUT':
        MensagemRede.objects.filter(id=msg_id).update(lida=True)
        return JsonResponse({'ok': True})
    return JsonResponse({'erro': 'Método não permitido'}, status=405)


# ─── PLANO DE SAÚDE ──────────────────────────────────────────────────────────

@csrf_exempt
def api_planos_saude(request):
    empresa = get_empresa(request)
    if not empresa:
        return JsonResponse({'erro': 'Não autenticado'}, status=401)

    if request.method == 'GET':
        planos = list(PlanoSaude.objects.filter(empresa=empresa).values(
            'id', 'nome', 'registro_ans', 'cnpj', 'modalidade',
            'telefone', 'email', 'site', 'abrangencia', 'status', 'criado_em'
        ))
        for p in planos:
            p['total_beneficiarios'] = BeneficiarioPlano.objects.filter(plano_id=p['id']).count()
            p['guias_pendentes'] = GuiaAutorizacao.objects.filter(plano_id=p['id'], status__in=['solicitada','em_analise']).count()
        return JsonResponse({'planos': planos})

    if request.method == 'POST':
        data = json.loads(request.body)
        p = PlanoSaude.objects.create(
            empresa=empresa,
            nome=data.get('nome', ''),
            registro_ans=data.get('registro_ans', ''),
            cnpj=data.get('cnpj', ''),
            modalidade=data.get('modalidade', ''),
            telefone=data.get('telefone', ''),
            email=data.get('email', ''),
            site=data.get('site', ''),
            abrangencia=data.get('abrangencia', 'nacional'),
        )
        return JsonResponse({'ok': True, 'id': p.id})

    return JsonResponse({'erro': 'Método não permitido'}, status=405)


@csrf_exempt
def api_plano_saude_detalhe(request, plano_id):
    empresa = get_empresa(request)
    if not empresa:
        return JsonResponse({'erro': 'Não autenticado'}, status=401)

    try:
        plano = PlanoSaude.objects.get(id=plano_id, empresa=empresa)
    except PlanoSaude.DoesNotExist:
        return JsonResponse({'erro': 'Não encontrado'}, status=404)

    if request.method == 'DELETE':
        plano.status = 'inativo'
        plano.save()
        return JsonResponse({'ok': True})

    return JsonResponse({'erro': 'Método não permitido'}, status=405)


# ─── BENEFICIÁRIOS ────────────────────────────────────────────────────────────

@csrf_exempt
def api_beneficiarios(request, plano_id):
    empresa = get_empresa(request)
    if not empresa:
        return JsonResponse({'erro': 'Não autenticado'}, status=401)

    try:
        plano = PlanoSaude.objects.get(id=plano_id, empresa=empresa)
    except PlanoSaude.DoesNotExist:
        return JsonResponse({'erro': 'Plano não encontrado'}, status=404)

    if request.method == 'GET':
        q = request.GET.get('q', '')
        qs = BeneficiarioPlano.objects.filter(plano=plano)
        if q:
            qs = qs.filter(Q(nome__icontains=q) | Q(cpf__icontains=q) | Q(numero_carteirinha__icontains=q))
        bens = list(qs.values(
            'id', 'nome', 'cpf', 'numero_carteirinha', 'data_nascimento',
            'sexo', 'telefone', 'email', 'situacao', 'plano_tipo', 'acomodacao',
            'data_inicio_vigencia', 'data_fim_vigencia'
        ))
        return JsonResponse({'beneficiarios': bens, 'total': len(bens)})

    if request.method == 'POST':
        data = json.loads(request.body)
        b = BeneficiarioPlano.objects.create(
            plano=plano,
            nome=data.get('nome', ''),
            cpf=data.get('cpf', ''),
            numero_carteirinha=data.get('numero_carteirinha', ''),
            data_nascimento=data.get('data_nascimento') or None,
            sexo=data.get('sexo', ''),
            telefone=data.get('telefone', ''),
            email=data.get('email', ''),
            situacao=data.get('situacao', 'ativo'),
            plano_tipo=data.get('plano_tipo', ''),
            acomodacao=data.get('acomodacao', 'enfermaria'),
            data_inicio_vigencia=data.get('data_inicio_vigencia') or None,
            data_fim_vigencia=data.get('data_fim_vigencia') or None,
        )
        return JsonResponse({'ok': True, 'id': b.id})

    return JsonResponse({'erro': 'Método não permitido'}, status=405)


@csrf_exempt
def api_beneficiario_detalhe(request, plano_id, ben_id):
    empresa = get_empresa(request)
    if not empresa:
        return JsonResponse({'erro': 'Não autenticado'}, status=401)

    try:
        plano = PlanoSaude.objects.get(id=plano_id, empresa=empresa)
        ben = BeneficiarioPlano.objects.get(id=ben_id, plano=plano)
    except (PlanoSaude.DoesNotExist, BeneficiarioPlano.DoesNotExist):
        return JsonResponse({'erro': 'Não encontrado'}, status=404)

    if request.method == 'PUT':
        data = json.loads(request.body)
        for field in ['nome','cpf','numero_carteirinha','sexo','telefone','email','situacao','plano_tipo','acomodacao']:
            if field in data:
                setattr(ben, field, data[field])
        for field in ['data_nascimento','data_inicio_vigencia','data_fim_vigencia']:
            if field in data:
                setattr(ben, field, data[field] or None)
        ben.save()
        return JsonResponse({'ok': True})

    if request.method == 'DELETE':
        ben.situacao = 'cancelado'
        ben.save()
        return JsonResponse({'ok': True})

    return JsonResponse({'erro': 'Método não permitido'}, status=405)


# ─── CARÊNCIA POR BENEFICIÁRIO ────────────────────────────────────────────────

@csrf_exempt
def api_carencias(request):
    """GET/POST /api/plano-saude/carencias/ — list or create carências"""
    from datetime import date
    empresa = get_empresa(request)
    if not empresa:
        return JsonResponse({'erro': 'Não autenticado'}, status=401)

    if request.method == 'GET':
        plano_id = request.GET.get('plano_id')
        beneficiario_id = request.GET.get('beneficiario_id')
        qs = CarenciaBeneficiario.objects.filter(empresa=empresa).select_related('beneficiario', 'beneficiario__plano')
        if plano_id:
            qs = qs.filter(beneficiario__plano_id=plano_id)
        if beneficiario_id:
            qs = qs.filter(beneficiario_id=beneficiario_id)
        return JsonResponse({'carencias': [{
            'id': c.id,
            'beneficiario_id': c.beneficiario_id,
            'beneficiario_nome': c.beneficiario.nome,
            'beneficiario_carteirinha': c.beneficiario.numero_carteirinha,
            'plano_nome': getattr(c.beneficiario.plano, 'nome', None)
                          or getattr(c.beneficiario.plano, 'nome_fantasia', None)
                          or '—',
            'tipo_procedimento': c.tipo_procedimento,
            'tipo_label': c.get_tipo_procedimento_display(),
            'data_inicio': c.data_inicio.isoformat(),
            'dias_carencia': c.dias_carencia,
            'data_fim': c.data_fim.isoformat(),
            'ativa': c.ativa,
            'dias_restantes': c.dias_restantes,
        } for c in qs]})

    if request.method == 'POST':
        try:
            data = json.loads(request.body)
        except Exception:
            return JsonResponse({'erro': 'JSON inválido'}, status=400)
        ben_id = data.get('beneficiario_id')
        tipo = data.get('tipo_procedimento')
        data_inicio = _parse_date_or_none(data.get('data_inicio'))
        dias = int(data.get('dias_carencia', 0))
        if not ben_id or not tipo or not data_inicio:
            return JsonResponse({'erro': 'beneficiario_id, tipo_procedimento e data_inicio são obrigatórios'}, status=400)
        try:
            beneficiario = BeneficiarioPlano.objects.get(id=ben_id, plano__empresa=empresa)
        except BeneficiarioPlano.DoesNotExist:
            return JsonResponse({'erro': 'Beneficiário não encontrado'}, status=404)
        c, created = CarenciaBeneficiario.objects.update_or_create(
            empresa=empresa,
            beneficiario=beneficiario,
            tipo_procedimento=tipo,
            defaults={
                'data_inicio': data_inicio,
                'dias_carencia': dias,
                'observacoes': data.get('observacoes', ''),
            }
        )
        return JsonResponse({'ok': True, 'id': c.id, 'criado': created}, status=201 if created else 200)

    return JsonResponse({'erro': 'Método não permitido'}, status=405)


@csrf_exempt
def api_carencia_detalhe(request, carencia_id):
    """DELETE /api/plano-saude/carencias/<id>/ — remove carência"""
    empresa = get_empresa(request)
    if not empresa:
        return JsonResponse({'erro': 'Não autenticado'}, status=401)
    try:
        c = CarenciaBeneficiario.objects.get(id=carencia_id, empresa=empresa)
    except CarenciaBeneficiario.DoesNotExist:
        return JsonResponse({'erro': 'Carência não encontrada'}, status=404)
    if request.method == 'DELETE':
        c.delete()
        return JsonResponse({'ok': True})
    return JsonResponse({'erro': 'Método não permitido'}, status=405)


@csrf_exempt
def api_portabilidade(request):
    """POST /api/plano-saude/portabilidade/ — transfer beneficiary between plans"""
    empresa = get_empresa(request)
    if not empresa:
        return JsonResponse({'erro': 'Não autenticado'}, status=401)
    if request.method != 'POST':
        return JsonResponse({'erro': 'Método não permitido'}, status=405)
    try:
        data = json.loads(request.body)
    except Exception:
        return JsonResponse({'erro': 'JSON inválido'}, status=400)
    ben_id = data.get('beneficiario_id')
    novo_plano_id = data.get('novo_plano_id')
    if not ben_id or not novo_plano_id:
        return JsonResponse({'erro': 'beneficiario_id e novo_plano_id são obrigatórios'}, status=400)
    try:
        ben = BeneficiarioPlano.objects.get(id=ben_id, plano__empresa=empresa)
    except BeneficiarioPlano.DoesNotExist:
        return JsonResponse({'erro': 'Beneficiário não encontrado'}, status=404)
    try:
        novo_plano = PlanoSaude.objects.get(id=novo_plano_id, empresa=empresa)
    except PlanoSaude.DoesNotExist:
        return JsonResponse({'erro': 'Novo plano não encontrado'}, status=404)
    plano_anterior = ben.plano
    ben.plano = novo_plano
    ben.data_inicio_vigencia = data.get('data_inicio') or ben.data_inicio_vigencia
    ben.save()
    return JsonResponse({
        'ok': True,
        'beneficiario': ben.nome,
        'plano_anterior': plano_anterior.nome_fantasia,
        'novo_plano': novo_plano.nome_fantasia,
    })


# ─── GUIAS DE AUTORIZAÇÃO ─────────────────────────────────────────────────────

@csrf_exempt
def api_guias(request, plano_id):
    empresa = get_empresa(request)
    if not empresa:
        return JsonResponse({'erro': 'Não autenticado'}, status=401)

    try:
        plano = PlanoSaude.objects.get(id=plano_id, empresa=empresa)
    except PlanoSaude.DoesNotExist:
        return JsonResponse({'erro': 'Plano não encontrado'}, status=404)

    if request.method == 'GET':
        status_f = request.GET.get('status', '')
        qs = GuiaAutorizacao.objects.filter(plano=plano).select_related('beneficiario')
        if status_f:
            qs = qs.filter(status=status_f)
        guias = []
        for g in qs:
            guias.append({
                'id': g.id,
                'tipo': g.tipo,
                'numero_guia': g.numero_guia,
                'codigo_procedimento': g.codigo_procedimento,
                'descricao_procedimento': g.descricao_procedimento,
                'cid': g.cid,
                'medico_solicitante': g.medico_solicitante,
                'crm_medico': g.crm_medico,
                'quantidade': g.quantidade,
                'valor_estimado': float(g.valor_estimado) if g.valor_estimado else None,
                'status': g.status,
                'numero_autorizacao': g.numero_autorizacao,
                'validade_autorizacao': str(g.validade_autorizacao) if g.validade_autorizacao else None,
                'justificativa_negativa': g.justificativa_negativa,
                'beneficiario_id': g.beneficiario_id,
                'beneficiario_nome': g.beneficiario.nome,
                'beneficiario_carteirinha': g.beneficiario.numero_carteirinha,
                'solicitada_em': g.solicitada_em.isoformat(),
                'atualizada_em': g.atualizada_em.isoformat(),
            })
        stats = {
            'solicitadas': GuiaAutorizacao.objects.filter(plano=plano, status='solicitada').count(),
            'em_analise': GuiaAutorizacao.objects.filter(plano=plano, status='em_analise').count(),
            'autorizadas': GuiaAutorizacao.objects.filter(plano=plano, status='autorizada').count(),
            'negadas': GuiaAutorizacao.objects.filter(plano=plano, status='negada').count(),
        }
        return JsonResponse({'guias': guias, 'stats': stats})

    if request.method == 'POST':
        data = json.loads(request.body)
        try:
            ben = BeneficiarioPlano.objects.get(id=data['beneficiario_id'], plano=plano)
        except BeneficiarioPlano.DoesNotExist:
            return JsonResponse({'erro': 'Beneficiário não encontrado'}, status=404)

        import uuid
        g = GuiaAutorizacao.objects.create(
            plano=plano,
            beneficiario=ben,
            tipo=data.get('tipo', 'consulta'),
            numero_guia=data.get('numero_guia', '') or f'GU{str(uuid.uuid4())[:8].upper()}',
            codigo_procedimento=data.get('codigo_procedimento', ''),
            descricao_procedimento=data.get('descricao_procedimento', ''),
            cid=data.get('cid', ''),
            medico_solicitante=data.get('medico_solicitante', ''),
            crm_medico=data.get('crm_medico', ''),
            quantidade=data.get('quantidade', 1),
            valor_estimado=data.get('valor_estimado') or None,
        )
        return JsonResponse({'ok': True, 'id': g.id, 'numero_guia': g.numero_guia})

    return JsonResponse({'erro': 'Método não permitido'}, status=405)


@csrf_exempt
def api_guia_detalhe(request, plano_id, guia_id):
    empresa = get_empresa(request)
    if not empresa:
        return JsonResponse({'erro': 'Não autenticado'}, status=401)

    try:
        plano = PlanoSaude.objects.get(id=plano_id, empresa=empresa)
        guia = GuiaAutorizacao.objects.get(id=guia_id, plano=plano)
    except (PlanoSaude.DoesNotExist, GuiaAutorizacao.DoesNotExist):
        return JsonResponse({'erro': 'Não encontrado'}, status=404)

    if request.method == 'PUT':
        data = json.loads(request.body)
        if 'status' in data:
            guia.status = data['status']
        if 'numero_autorizacao' in data:
            guia.numero_autorizacao = data['numero_autorizacao']
        if 'validade_autorizacao' in data:
            guia.validade_autorizacao = data['validade_autorizacao'] or None
        if 'justificativa_negativa' in data:
            guia.justificativa_negativa = data['justificativa_negativa']
        guia.save()
        return JsonResponse({'ok': True})

    if request.method == 'DELETE':
        guia.status = 'cancelada'
        guia.save()
        return JsonResponse({'ok': True})

    return JsonResponse({'erro': 'Método não permitido'}, status=405)


# ─── KPIs PLANO DE SAÚDE ─────────────────────────────────────────────────────

def api_plano_kpis(request, plano_id):
    empresa = get_empresa(request)
    if not empresa:
        return JsonResponse({'erro': 'Não autenticado'}, status=401)

    try:
        plano = PlanoSaude.objects.get(id=plano_id, empresa=empresa)
    except PlanoSaude.DoesNotExist:
        return JsonResponse({'erro': 'Não encontrado'}, status=404)

    total_bens = BeneficiarioPlano.objects.filter(plano=plano).count()
    ativos = BeneficiarioPlano.objects.filter(plano=plano, situacao='ativo').count()
    guias_pendentes = GuiaAutorizacao.objects.filter(plano=plano, status__in=['solicitada','em_analise']).count()
    guias_autorizadas = GuiaAutorizacao.objects.filter(plano=plano, status='autorizada').count()
    guias_negadas = GuiaAutorizacao.objects.filter(plano=plano, status='negada').count()

    return JsonResponse({
        'total_beneficiarios': total_bens,
        'beneficiarios_ativos': ativos,
        'guias_pendentes': guias_pendentes,
        'guias_autorizadas': guias_autorizadas,
        'guias_negadas': guias_negadas,
    })
"""
Dashboard Executivo de Rede — comparação entre unidades, ranking e KPIs consolidados.
Endpoint: GET /api/rede/kpis
Page:     GET /dashboard-rede/

Nota: apesar do nome do endpoint, isto consolida EmpresaUnidade (multi-unidade
corporativa de SST/bem-estar), NÃO UnidadeRede (rede de Hospital/Farmácia do
setor "rede"). Para benchmarking/KPIs consolidados da rede Hospital/Farmácia,
ver api_rede_hospital_kpis (acima) e o painel central de Farmácia.
"""
from datetime import date, timedelta
from django.http import JsonResponse
from django.db.models import Avg, Count, Q
from .views_dashboard import _empresa_autenticada


def api_rede_kpis(request):
    empresa = _empresa_autenticada(request)
    if not empresa:
        return JsonResponse({"erro": "Não autenticado"}, status=401)

    hoje = date.today()
    semana_ini = hoje - timedelta(days=hoje.weekday())
    mes_ini = hoje.replace(day=1)
    ultimos_7 = hoje - timedelta(days=6)
    ultimos_30 = hoje - timedelta(days=29)

    unidades = list(empresa.unidades_corporativas.filter(ativo=True).order_by("nome"))

    # ── Consolidated totals ──────────────────────────────────────────────────
    try:
        from .models import FuncionarioSST, CheckinDiarioCorporativo, CheckinSemanalCorporativo, PedidoApoioCorporativo

        total_func = FuncionarioSST.objects.filter(empresa=empresa, ativo=True).count()

        checkins_mes = CheckinDiarioCorporativo.objects.filter(
            empresa=empresa, data_referencia__gte=mes_ini
        )
        avg_bem_estar = checkins_mes.aggregate(
            humor=Avg("humor"), energia=Avg("energia"),
            estresse=Avg("estresse"), sono=Avg("sono"),
        )
        bem_estar_geral = round(
            ((avg_bem_estar["humor"] or 0) + (avg_bem_estar["energia"] or 0)
             + (avg_bem_estar["sono"] or 0)
             + (5 - (avg_bem_estar["estresse"] or 3))) / 4, 1
        ) if checkins_mes.exists() else None

        semanais_mes = CheckinSemanalCorporativo.objects.filter(
            empresa=empresa, semana_referencia__gte=mes_ini
        )
        risco_burnout_pct = None
        if semanais_mes.exists():
            alto_risco = semanais_mes.filter(risco_burnout__gte=4).count()
            risco_burnout_pct = round(alto_risco / semanais_mes.count() * 100)

        apoios_abertos = PedidoApoioCorporativo.objects.filter(
            empresa=empresa,
            status__in=["novo", "em_analise"]
        ).count()

        checkins_hoje = CheckinDiarioCorporativo.objects.filter(
            empresa=empresa, data_referencia=hoje
        ).count()

    except Exception:
        total_func = 0
        bem_estar_geral = None
        risco_burnout_pct = None
        apoios_abertos = 0
        checkins_hoje = 0

    # ── Per-unit breakdown ───────────────────────────────────────────────────
    unidades_data = []
    for u in unidades:
        try:
            func_count = FuncionarioSST.objects.filter(empresa=empresa, unidade=u, ativo=True).count()

            checkins_u = CheckinDiarioCorporativo.objects.filter(
                empresa=empresa, unidade=u, data_referencia__gte=ultimos_7
            )
            avg_u = checkins_u.aggregate(
                humor=Avg("humor"), energia=Avg("energia"),
                estresse=Avg("estresse"), sono=Avg("sono"),
            )
            score = None
            if checkins_u.exists():
                score = round(
                    ((avg_u["humor"] or 0) + (avg_u["energia"] or 0)
                     + (avg_u["sono"] or 0)
                     + (5 - (avg_u["estresse"] or 3))) / 4, 1
                )

            semanais_u = CheckinSemanalCorporativo.objects.filter(
                empresa=empresa, unidade=u, semana_referencia__gte=mes_ini
            )
            burnout_u = None
            if semanais_u.exists():
                alto = semanais_u.filter(risco_burnout__gte=4).count()
                burnout_u = round(alto / semanais_u.count() * 100)

            apoios_u = PedidoApoioCorporativo.objects.filter(
                empresa=empresa, unidade=u, status__in=["novo", "em_analise"]
            ).count()

            checkins_u_hoje = CheckinDiarioCorporativo.objects.filter(
                empresa=empresa, unidade=u, data_referencia=hoje
            ).count()

            adesao = round(checkins_u_hoje / func_count * 100) if func_count > 0 else 0

        except Exception:
            func_count = 0
            score = None
            burnout_u = None
            apoios_u = 0
            adesao = 0

        unidades_data.append({
            "id": u.id,
            "nome": u.nome,
            "codigo": u.codigo or "",
            "funcionarios": func_count,
            "score_bem_estar": score,
            "risco_burnout_pct": burnout_u,
            "apoios_abertos": apoios_u,
            "adesao_hoje_pct": adesao,
        })

    # Sort by score descending (best units first)
    unidades_data.sort(key=lambda x: (x["score_bem_estar"] or 0), reverse=True)

    # ── 30-day trend (company-wide daily avg) ────────────────────────────────
    tendencia = []
    try:
        for delta in range(29, -1, -1):
            d = hoje - timedelta(days=delta)
            dias_checkins = CheckinDiarioCorporativo.objects.filter(
                empresa=empresa, data_referencia=d
            )
            if dias_checkins.exists():
                avg_d = dias_checkins.aggregate(
                    humor=Avg("humor"), energia=Avg("energia"),
                    estresse=Avg("estresse"), sono=Avg("sono"),
                )
                score_d = round(
                    ((avg_d["humor"] or 0) + (avg_d["energia"] or 0)
                     + (avg_d["sono"] or 0)
                     + (5 - (avg_d["estresse"] or 3))) / 4, 2
                )
                tendencia.append({"data": str(d), "score": score_d, "checkins": dias_checkins.count()})
            else:
                tendencia.append({"data": str(d), "score": None, "checkins": 0})
    except Exception:
        tendencia = []

    return JsonResponse({
        "empresa": empresa.nome,
        "data": str(hoje),
        "total_unidades": len(unidades),
        "total_funcionarios": total_func,
        "bem_estar_geral": bem_estar_geral,
        "risco_burnout_pct": risco_burnout_pct,
        "apoios_abertos": apoios_abertos,
        "checkins_hoje": checkins_hoje,
        "unidades": unidades_data,
        "tendencia_30d": tendencia,
    })


def dashboard_rede_page(request):
    from django.shortcuts import render
    return render(request, "dashboard_rede.html")


def api_rede_sala_situacao(request):
    """GET /api/rede/sala-situacao/ — painel situacional consolidado da rede (unidades críticas, transferências urgentes, alertas)."""
    from .models import ItemFarmacia, LeitoHospitalar, TriagemManchester
    from .access_control import empresa_tem_feature

    empresa, err = _verificar_acesso_rede(request)
    if err:
        return err

    setor = get_setor(empresa)
    feature_situacao = {
        "hospital": "hospital.painel_executivo",
        "farmacia": "farmacia.painel_central",
    }.get(setor, "rede.sala_situacao")
    if not empresa_tem_feature(empresa, feature_situacao):
        return JsonResponse({
            "erro": "Sala de Situação não disponível no seu plano atual.",
            "feature_requerida": feature_situacao,
            "upgrade_necessario": True,
        }, status=403)

    unidade = get_unidade(empresa)
    if not unidade or not unidade.rede:
        return JsonResponse({"rede": None, "nivel_situacional": "verde", "unidades_criticas": [], "transferencias_urgentes": [], "alertas_recentes": []})

    rede = unidade.rede
    unidades_rede = rede.unidades.filter(ativa=True)

    unidades_criticas = []
    for u in unidades_rede:
        emp = u.empresa
        if u.tipo == "hospital":
            total_leitos = LeitoHospitalar.objects.filter(empresa=emp).count()
            ocupados = LeitoHospitalar.objects.filter(empresa=emp, status="ocupado").count()
            taxa = round(ocupados / total_leitos * 100, 1) if total_leitos else 0.0
            triagens_vermelhas = TriagemManchester.objects.filter(
                empresa=emp, nivel="vermelho", status__in=["aguardando", "em_atendimento"]
            ).count()
            if taxa >= 90 or triagens_vermelhas > 0:
                unidades_criticas.append({
                    "unidade_id": u.id, "unidade_nome": u.nome_unidade or emp.nome, "tipo": "hospital",
                    "motivo": f"Ocupação {taxa}%" + (f" · {triagens_vermelhas} triagem(ns) vermelha(s) pendente(s)" if triagens_vermelhas else ""),
                    "nivel": "vermelho" if (taxa >= 95 or triagens_vermelhas > 0) else "laranja",
                })
        else:
            itens_criticos = ItemFarmacia.objects.filter(empresa=emp, ativo=True, estoque_atual__lte=F("estoque_minimo")).count()
            if itens_criticos > 0:
                unidades_criticas.append({
                    "unidade_id": u.id, "unidade_nome": u.nome_unidade or emp.nome, "tipo": "farmacia",
                    "motivo": f"{itens_criticos} item(ns) em estoque crítico",
                    "nivel": "vermelho" if itens_criticos >= 5 else "laranja",
                })

    transferencias_urgentes_qs = TransferenciaEstoque.objects.filter(
        rede=rede, urgente=True, status__in=["pendente", "aprovada"]
    ).select_related("unidade_solicitante", "unidade_fornecedora").order_by("-solicitado_em")
    transferencias_urgentes = [{
        "id": t.id, "item": t.nome_item or (t.item_farmacia.nome if t.item_farmacia else ""),
        "solicitante": t.unidade_solicitante.nome_unidade, "fornecedora": t.unidade_fornecedora.nome_unidade,
        "status": t.status, "solicitado_em": t.solicitado_em.isoformat(),
    } for t in transferencias_urgentes_qs[:50]]

    alertas_qs = MensagemRede.objects.filter(rede=rede, tipo="alerta").select_related("remetente").order_by("-enviada_em")[:20]
    alertas_recentes = [{
        "id": a.id, "assunto": a.assunto, "corpo": a.corpo,
        "remetente": a.remetente.nome_unidade, "lida": a.lida, "enviada_em": a.enviada_em.isoformat(),
    } for a in alertas_qs]

    vermelhos = sum(1 for u in unidades_criticas if u["nivel"] == "vermelho")
    if vermelhos > 0:
        nivel_situacional = "vermelho"
    elif unidades_criticas or transferencias_urgentes:
        nivel_situacional = "laranja"
    elif alertas_recentes:
        nivel_situacional = "amarelo"
    else:
        nivel_situacional = "verde"

    return JsonResponse({
        "rede": rede.nome,
        "nivel_situacional": nivel_situacional,
        "unidades_criticas": unidades_criticas,
        "transferencias_urgentes": transferencias_urgentes,
        "alertas_recentes": alertas_recentes,
    })
