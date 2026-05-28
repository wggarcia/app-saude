import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../servicos/funcionario_sst_service.dart';

class TelaComunicados extends StatefulWidget {
  const TelaComunicados({super.key});

  @override
  State<TelaComunicados> createState() => _TelaComunicadosState();
}

class _TelaComunicadosState extends State<TelaComunicados> {
  List<Map<String, dynamic>> _lista = [];
  String? _erro;
  bool _loading = true;
  int _naoLidos = 0;

  static const _teal = Color(0xFF27D3BE);
  static const _surface = Color(0xFF102A32);
  static const _amber = Color(0xFFFFB454);
  static const _blue = Color(0xFF52A6FF);

  @override
  void initState() {
    super.initState();
    _carregar();
  }

  Future<void> _carregar() async {
    setState(() {
      _loading = true;
      _erro = null;
    });
    try {
      final data = await FuncionarioSstService.comunicados();
      if (!mounted) return;
      final lista = List<Map<String, dynamic>>.from(
          (data['comunicados'] ?? data['mensagens'] ?? data['results'] ?? [])
              .map((e) => e as Map<String, dynamic>));
      setState(() {
        _lista = lista;
        _naoLidos = lista.where((c) => c['lido'] == false).length;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() => _erro = e.toString().replaceFirst('Exception: ', ''));
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _marcarLido(Map<String, dynamic> comunicado) async {
    if (comunicado['lido'] == true) return;
    try {
      await FuncionarioSstService.marcarComunicadoLido(comunicado['id'] as int);
      setState(() {
        comunicado['lido'] = true;
        _naoLidos = (_naoLidos - 1).clamp(0, 999);
      });
    } catch (_) {}
  }

  // ── Determina icone/cor pelo tipo de comunicado ───────────────────────
  _TipoCom _tipo(Map<String, dynamic> c) {
    final t = (c['tipo'] ?? c['categoria'] ?? 'geral').toString().toLowerCase();
    if (t.contains('urgente') || t.contains('emergenc')) {
      return _TipoCom(Icons.warning_amber_rounded, const Color(0xFFFF6B6B),
          'Urgente');
    }
    if (t.contains('treina')) {
      return _TipoCom(Icons.school_outlined, _teal, 'Treinamento');
    }
    if (t.contains('epi') || t.contains('equip')) {
      return _TipoCom(Icons.security_outlined, _teal, 'EPI');
    }
    if (t.contains('exame') || t.contains('aso') || t.contains('saude')) {
      return _TipoCom(Icons.medical_information_outlined, _blue, 'Saúde');
    }
    if (t.contains('pgr') || t.contains('risco')) {
      return _TipoCom(Icons.gpp_maybe_outlined, _amber, 'Risco');
    }
    if (t.contains('reuni')) {
      return _TipoCom(Icons.groups_outlined, _blue, 'Reunião');
    }
    return _TipoCom(Icons.campaign_outlined, Colors.white54, 'Geral');
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Row(
          children: [
            const Text('Comunicados SST'),
            if (_naoLidos > 0) ...[
              const SizedBox(width: 8),
              Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 7, vertical: 2),
                decoration: BoxDecoration(
                  color: _teal.withValues(alpha: 0.2),
                  borderRadius: BorderRadius.circular(999),
                ),
                child: Text('$_naoLidos',
                    style: const TextStyle(
                        color: _teal,
                        fontWeight: FontWeight.w800,
                        fontSize: 11)),
              ),
            ],
          ],
        ),
        actions: [
          IconButton(
              icon: const Icon(Icons.refresh),
              onPressed: _carregar,
              tooltip: 'Atualizar'),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _erro != null
              ? _buildErro()
              : _buildLista(),
    );
  }

  Widget _buildErro() {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.cloud_off_outlined,
                size: 48, color: Colors.white38),
            const SizedBox(height: 12),
            Text(_erro!,
                textAlign: TextAlign.center,
                style: const TextStyle(color: Colors.white60)),
            const SizedBox(height: 16),
            FilledButton.icon(
              onPressed: _carregar,
              icon: const Icon(Icons.refresh),
              label: const Text('Tentar novamente'),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildLista() {
    if (_lista.isEmpty) {
      return const Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.campaign_outlined, size: 56, color: Colors.white24),
            SizedBox(height: 12),
            Text('Nenhum comunicado.',
                style: TextStyle(color: Colors.white38, fontSize: 15)),
            SizedBox(height: 6),
            Text('Os comunicados da empresa aparecerão aqui.',
                style: TextStyle(color: Colors.white24, fontSize: 12)),
          ],
        ),
      );
    }

    return RefreshIndicator(
      onRefresh: _carregar,
      child: ListView.separated(
        padding: const EdgeInsets.all(16),
        itemCount: _lista.length,
        separatorBuilder: (_, __) => const SizedBox(height: 10),
        itemBuilder: (ctx, i) {
          final c = _lista[i];
          final tp = _tipo(c);
          final titulo =
              (c['titulo'] ?? c['assunto'] ?? 'Comunicado').toString();
          final corpo = (c['corpo'] ?? c['mensagem'] ?? c['texto'] ?? '')
              .toString();
          final data = (c['criado_em'] ?? c['data'] ?? '').toString();
          final lido = c['lido'] == true;
          final linkAnexo = (c['link'] ?? c['arquivo_url'] ?? '').toString();

          return GestureDetector(
            onTap: () {
              _marcarLido(c);
              _abrirDetalhe(ctx, c, tp);
            },
            child: AnimatedContainer(
              duration: const Duration(milliseconds: 200),
              decoration: BoxDecoration(
                color: lido
                    ? _surface
                    : const Color(0xFF152E38),
                borderRadius: BorderRadius.circular(16),
                border: Border(
                  left: BorderSide(
                      color: lido
                          ? Colors.white12
                          : tp.color,
                      width: lido ? 2 : 4),
                ),
              ),
              child: Padding(
                padding: const EdgeInsets.all(14),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(children: [
                      Container(
                        width: 32,
                        height: 32,
                        decoration: BoxDecoration(
                          color: tp.color.withValues(alpha: 0.13),
                          borderRadius: BorderRadius.circular(8),
                        ),
                        child:
                            Icon(tp.icon, color: tp.color, size: 17),
                      ),
                      const SizedBox(width: 10),
                      Expanded(
                        child: Text(titulo,
                            style: TextStyle(
                                color: lido
                                    ? Colors.white60
                                    : Colors.white,
                                fontWeight: lido
                                    ? FontWeight.w500
                                    : FontWeight.w800,
                                fontSize: 14)),
                      ),
                      if (!lido)
                        Container(
                          width: 8,
                          height: 8,
                          decoration: BoxDecoration(
                              color: tp.color,
                              shape: BoxShape.circle),
                        ),
                    ]),
                    if (corpo.isNotEmpty) ...[
                      const SizedBox(height: 8),
                      Text(
                        corpo,
                        maxLines: 2,
                        overflow: TextOverflow.ellipsis,
                        style: const TextStyle(
                            color: Colors.white38, fontSize: 12, height: 1.4),
                      ),
                    ],
                    const SizedBox(height: 8),
                    Row(
                      children: [
                        Container(
                          padding: const EdgeInsets.symmetric(
                              horizontal: 7, vertical: 3),
                          decoration: BoxDecoration(
                            color: tp.color.withValues(alpha: 0.1),
                            borderRadius: BorderRadius.circular(6),
                          ),
                          child: Text(tp.label,
                              style: TextStyle(
                                  color: tp.color,
                                  fontSize: 10,
                                  fontWeight: FontWeight.w700)),
                        ),
                        const Spacer(),
                        if (data.isNotEmpty)
                          Text(
                            data.length > 10 ? data.substring(0, 10) : data,
                            style: const TextStyle(
                                color: Colors.white24, fontSize: 11),
                          ),
                      ],
                    ),
                    if (linkAnexo.isNotEmpty && linkAnexo != 'null') ...[
                      const SizedBox(height: 8),
                      Row(
                        children: [
                          const Icon(Icons.attach_file_outlined,
                              size: 13, color: Colors.white38),
                          const SizedBox(width: 4),
                          Text('Ver anexo',
                              style: TextStyle(
                                  color: tp.color,
                                  fontSize: 11,
                                  fontWeight: FontWeight.w600)),
                        ],
                      ),
                    ],
                  ],
                ),
              ),
            ),
          );
        },
      ),
    );
  }

  void _abrirDetalhe(
      BuildContext ctx, Map<String, dynamic> c, _TipoCom tp) {
    final titulo =
        (c['titulo'] ?? c['assunto'] ?? 'Comunicado').toString();
    final corpo =
        (c['corpo'] ?? c['mensagem'] ?? c['texto'] ?? '').toString();
    final data = (c['criado_em'] ?? c['data'] ?? '').toString();
    final linkAnexo = (c['link'] ?? c['arquivo_url'] ?? '').toString();
    final remetente =
        (c['remetente'] ?? c['enviado_por'] ?? 'Empresa').toString();

    showModalBottomSheet(
      context: ctx,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (_) => DraggableScrollableSheet(
        initialChildSize: 0.65,
        minChildSize: 0.4,
        maxChildSize: 0.92,
        builder: (_, scroll) => Container(
          decoration: const BoxDecoration(
            color: Color(0xFF0D1F28),
            borderRadius:
                BorderRadius.vertical(top: Radius.circular(22)),
          ),
          child: Column(
            children: [
              // Handle
              Container(
                margin: const EdgeInsets.only(top: 10, bottom: 6),
                width: 38,
                height: 4,
                decoration: BoxDecoration(
                  color: Colors.white24,
                  borderRadius: BorderRadius.circular(2),
                ),
              ),
              Expanded(
                child: ListView(
                  controller: scroll,
                  padding: const EdgeInsets.fromLTRB(20, 8, 20, 24),
                  children: [
                    Row(children: [
                      Container(
                        width: 38,
                        height: 38,
                        decoration: BoxDecoration(
                          color: tp.color.withValues(alpha: 0.15),
                          borderRadius: BorderRadius.circular(10),
                        ),
                        child:
                            Icon(tp.icon, color: tp.color, size: 20),
                      ),
                      const SizedBox(width: 12),
                      Expanded(
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(tp.label,
                                style: TextStyle(
                                    color: tp.color,
                                    fontSize: 10,
                                    fontWeight: FontWeight.w800,
                                    letterSpacing: 0.8)),
                            Text(titulo,
                                style: const TextStyle(
                                    color: Colors.white,
                                    fontWeight: FontWeight.w800,
                                    fontSize: 16)),
                          ],
                        ),
                      ),
                    ]),
                    const SizedBox(height: 16),
                    if (corpo.isNotEmpty) ...[
                      Text(corpo,
                          style: const TextStyle(
                              color: Colors.white70,
                              fontSize: 14,
                              height: 1.6)),
                      const SizedBox(height: 16),
                    ],
                    Row(children: [
                      const Icon(Icons.person_outline,
                          size: 13, color: Colors.white38),
                      const SizedBox(width: 5),
                      Text(remetente,
                          style: const TextStyle(
                              color: Colors.white38, fontSize: 12)),
                      const Spacer(),
                      const Icon(Icons.calendar_today_outlined,
                          size: 12, color: Colors.white24),
                      const SizedBox(width: 4),
                      Text(
                          data.length > 10
                              ? data.substring(0, 10)
                              : data,
                          style: const TextStyle(
                              color: Colors.white24, fontSize: 11)),
                    ]),
                    if (linkAnexo.isNotEmpty &&
                        linkAnexo != 'null') ...[
                      const SizedBox(height: 16),
                      FilledButton.icon(
                        style: FilledButton.styleFrom(
                          backgroundColor: tp.color,
                          foregroundColor: const Color(0xFF041018),
                          padding: const EdgeInsets.symmetric(
                              vertical: 13),
                          shape: RoundedRectangleBorder(
                              borderRadius: BorderRadius.circular(12)),
                        ),
                        onPressed: () async {
                          final uri = Uri.tryParse(linkAnexo);
                          if (uri != null &&
                              await canLaunchUrl(uri)) {
                            await launchUrl(uri,
                                mode: LaunchMode
                                    .externalApplication);
                          }
                        },
                        icon: const Icon(
                            Icons.open_in_new_outlined,
                            size: 16),
                        label: const Text('Ver anexo / link',
                            style: TextStyle(
                                fontWeight: FontWeight.w800)),
                      ),
                    ],
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _TipoCom {
  const _TipoCom(this.icon, this.color, this.label);
  final IconData icon;
  final Color color;
  final String label;
}
