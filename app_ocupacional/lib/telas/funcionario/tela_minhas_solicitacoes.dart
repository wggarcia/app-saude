import 'package:flutter/material.dart';

import '../../servicos/funcionario_sst_service.dart';

class TelaMinhasSolicitacoes extends StatefulWidget {
  const TelaMinhasSolicitacoes({super.key});

  @override
  State<TelaMinhasSolicitacoes> createState() => _TelaMinhasSolicitacoesState();
}

class _TelaMinhasSolicitacoesState extends State<TelaMinhasSolicitacoes> {
  List<dynamic> _lista = const [];
  String? _erro;
  bool _loading = true;

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
      final data = await FuncionarioSstService.solicitacoes();
      if (!mounted) return;
      setState(() => _lista = (data['solicitacoes'] as List<dynamic>? ?? []));
    } catch (e) {
      if (!mounted) return;
      setState(() => _erro = e.toString().replaceFirst('Exception: ', ''));
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  _StatusInfo _statusInfo(String rawStatus) {
    final s = rawStatus.toLowerCase().trim();
    if (s.contains('agendado') || s.contains('scheduled')) {
      return _StatusInfo(label: 'Agendado', color: const Color(0xFF27D3BE), icon: Icons.event_available_outlined);
    }
    if (s.contains('conclu') || s.contains('finaliz') || s.contains('realiz')) {
      return _StatusInfo(label: 'Concluído', color: const Color(0xFF4CAF50), icon: Icons.check_circle_outline);
    }
    if (s.contains('cancel')) {
      return _StatusInfo(label: 'Cancelado', color: const Color(0xFFFF6B6B), icon: Icons.cancel_outlined);
    }
    if (s.contains('em_andamento') || s.contains('andamento')) {
      return _StatusInfo(label: 'Em andamento', color: const Color(0xFF27D3BE), icon: Icons.pending_outlined);
    }
    if (s.contains('aprovado') || s.contains('aprovad')) {
      return _StatusInfo(label: 'Aprovado', color: const Color(0xFF27D3BE), icon: Icons.thumb_up_alt_outlined);
    }
    if (s.contains('reprov') || s.contains('recusado') || s.contains('negado')) {
      return _StatusInfo(label: 'Reprovado', color: const Color(0xFFFF6B6B), icon: Icons.thumb_down_alt_outlined);
    }
    if (s.contains('pendente') || s.isEmpty) {
      return _StatusInfo(label: 'Pendente', color: const Color(0xFFFFB454), icon: Icons.hourglass_empty_outlined);
    }
    return _StatusInfo(label: rawStatus, color: Colors.white38, icon: Icons.info_outline);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Meus Exames'),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: _carregar,
            tooltip: 'Atualizar',
          ),
        ],
      ),
      body: _buildBody(),
    );
  }

  Widget _buildBody() {
    if (_loading) return const Center(child: CircularProgressIndicator());

    if (_erro != null) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.cloud_off_outlined, size: 48, color: Colors.white38),
              const SizedBox(height: 12),
              Text(_erro!, textAlign: TextAlign.center, style: const TextStyle(color: Colors.white60)),
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

    if (_lista.isEmpty) {
      return const Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.medical_services_outlined, size: 56, color: Colors.white24),
            SizedBox(height: 12),
            Text('Nenhuma solicitação de exame encontrada.',
              style: TextStyle(color: Colors.white38, fontSize: 15), textAlign: TextAlign.center),
            SizedBox(height: 6),
            Text('Suas solicitações aparecerão aqui quando forem abertas.',
              style: TextStyle(color: Colors.white24, fontSize: 12), textAlign: TextAlign.center),
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
        itemBuilder: (_, i) {
          final item = _lista[i] as Map<String, dynamic>;
          final rawStatus = (item['status_display'] ?? item['status'] ?? 'pendente').toString();
          final status = _statusInfo(rawStatus);
          return _SolicitacaoCard(item: item, status: status);
        },
      ),
    );
  }
}

class _StatusInfo {
  const _StatusInfo({required this.label, required this.color, required this.icon});
  final String label;
  final Color color;
  final IconData icon;
}

class _SolicitacaoCard extends StatelessWidget {
  const _SolicitacaoCard({required this.item, required this.status});
  final Map<String, dynamic> item;
  final _StatusInfo status;

  @override
  Widget build(BuildContext context) {
    final tipo = (item['tipo_aso_display'] ?? item['tipo_aso'] ?? 'Solicitação').toString();
    final clinica = (item['clinica_nome'] ?? item['destino'] ?? 'Operação interna').toString();
    final dataAgendamento = (item['data_agendamento'] ?? '').toString();
    final dataSolicitacao = (item['data_solicitacao'] ?? item['criado_em'] ?? '').toString();
    final observacao = (item['observacao'] ?? item['obs'] ?? '').toString();
    final protocolo = (item['protocolo'] ?? item['codigo'] ?? '').toString();

    return Container(
      decoration: BoxDecoration(
        color: const Color(0xFF102A32),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: status.color.withValues(alpha: 0.25),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // ── Cabeçalho colorido ──
          Container(
            padding: const EdgeInsets.fromLTRB(14, 12, 14, 12),
            decoration: BoxDecoration(
              color: status.color.withValues(alpha: 0.1),
              borderRadius: const BorderRadius.vertical(top: Radius.circular(16)),
            ),
            child: Row(
              children: [
                Icon(Icons.medical_services_outlined, color: status.color, size: 18),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(tipo,
                    style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 14, color: Colors.white)),
                ),
                _StatusChip(status: status),
              ],
            ),
          ),
          // ── Detalhes ──
          Padding(
            padding: const EdgeInsets.all(14),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                if (clinica.isNotEmpty) ...[
                  _Row(icon: Icons.local_hospital_outlined, label: 'Clínica', value: clinica),
                  const SizedBox(height: 6),
                ],
                if (dataSolicitacao.isNotEmpty && dataSolicitacao != 'null') ...[
                  _Row(icon: Icons.calendar_today_outlined, label: 'Solicitado em', value: dataSolicitacao),
                  const SizedBox(height: 6),
                ],
                if (dataAgendamento.isNotEmpty && dataAgendamento != 'null') ...[
                  _Row(
                    icon: Icons.event_available_outlined,
                    label: 'Agendado para',
                    value: dataAgendamento,
                    valueColor: const Color(0xFF27D3BE),
                  ),
                  const SizedBox(height: 6),
                ],
                if (protocolo.isNotEmpty && protocolo != 'null')
                  _Row(icon: Icons.tag, label: 'Protocolo', value: protocolo),
                if (observacao.isNotEmpty && observacao != 'null') ...[
                  const SizedBox(height: 10),
                  const Divider(height: 1, color: Colors.white12),
                  const SizedBox(height: 10),
                  Text(observacao, style: const TextStyle(color: Colors.white54, fontSize: 12, height: 1.4)),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _StatusChip extends StatelessWidget {
  const _StatusChip({required this.status});
  final _StatusInfo status;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: status.color.withValues(alpha: 0.18),
        borderRadius: BorderRadius.circular(999),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(status.icon, color: status.color, size: 12),
          const SizedBox(width: 4),
          Text(status.label,
            style: TextStyle(
              color: status.color,
              fontSize: 11,
              fontWeight: FontWeight.w700,
            )),
        ],
      ),
    );
  }
}

class _Row extends StatelessWidget {
  const _Row({required this.icon, required this.label, required this.value, this.valueColor});
  final IconData icon;
  final String label;
  final String value;
  final Color? valueColor;

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Icon(icon, size: 14, color: Colors.white38),
        const SizedBox(width: 6),
        SizedBox(width: 88, child: Text(label, style: const TextStyle(color: Colors.white38, fontSize: 12))),
        Expanded(
          child: Text(value,
            style: TextStyle(
              color: valueColor ?? Colors.white70,
              fontSize: 13,
              fontWeight: FontWeight.w500,
            )),
        ),
      ],
    );
  }
}
