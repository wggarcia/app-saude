import json
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.views.decorators.csrf import csrf_exempt
from django.db.models import Q, Sum
from .models import (
    Empresa, Rede, UnidadeRede, TransferenciaEstoque, MensagemRede,
    PlanoSaude, BeneficiarioPlano, GuiaAutorizacao, ItemFarmacia,
)


def get_empresa(request):
    eid = request.session.get('empresa_id')
    if not eid:
        return None
    try:
        return Empresa.objects.get(id=eid)
    except Empresa.DoesNotExist:
        return None


def get_unidade(empresa):
    """Get or create UnidadeRede for this empresa."""
    try:
        return UnidadeRede.objects.get(empresa=empresa)
    except UnidadeRede.DoesNotExist:
        return None


# ─── REDE ────────────────────────────────────────────────────────────────────

@csrf_exempt
def api_redes(request):
    empresa = get_empresa(request)
    if not empresa:
        return JsonResponse({'erro': 'Não autenticado'}, status=401)

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
    empresa = get_empresa(request)
    if not empresa:
        return JsonResponse({'erro': 'Não autenticado'}, status=401)

    unidade = get_unidade(empresa)
    if not unidade or not unidade.rede:
        return JsonResponse({'erro': 'Você não pertence a uma rede'}, status=400)

    if request.method == 'POST':
        data = json.loads(request.body)
        # Register another empresa (by email) into the same network
        email_destino = data.get('email_empresa', '')
        try:
            empresa_destino = Empresa.objects.get(email=email_destino)
        except Empresa.DoesNotExist:
            return JsonResponse({'erro': f'Empresa com email {email_destino} não encontrada'}, status=404)

        u, created = UnidadeRede.objects.get_or_create(empresa=empresa_destino)
        u.rede = unidade.rede
        u.tipo = data.get('tipo', 'farmacia')
        u.nome_unidade = data.get('nome_unidade', empresa_destino.nome)
        u.codigo_unidade = data.get('codigo_unidade', '')
        u.save()
        return JsonResponse({'ok': True, 'criada': created, 'unidade_id': u.id})

    return JsonResponse({'erro': 'Método não permitido'}, status=405)


# ─── ESTOQUE CONSOLIDADO DA REDE ─────────────────────────────────────────────

def api_rede_estoque(request):
    empresa = get_empresa(request)
    if not empresa:
        return JsonResponse({'erro': 'Não autenticado'}, status=401)

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
    empresa = get_empresa(request)
    if not empresa:
        return JsonResponse({'erro': 'Não autenticado'}, status=401)

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


# ─── TRANSFERÊNCIAS ───────────────────────────────────────────────────────────

@csrf_exempt
def api_transferencias(request):
    empresa = get_empresa(request)
    if not empresa:
        return JsonResponse({'erro': 'Não autenticado'}, status=401)

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
