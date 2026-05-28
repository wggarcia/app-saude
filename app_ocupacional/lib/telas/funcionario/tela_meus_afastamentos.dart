import 'package:flutter/material.dart';

import '../../servicos/funcionario_sst_service.dart';

/// Exibe os afastamentos do funcionário autenticado.
class TelaMeusAfastamentos extends StatefulWidget {
  const TelaMeusAfastamentos({super.key});

  @override
  State<TelaMeusAfastamentos> createState() => _TelaMeusAfastamentosState();
}

class _TelaMeusAfastamentosState extends State<TelaMeusAfastamentos> {
  List<dynamic> _lista = const [];
  bool _loading = true;
  String? _erro;

  // ── Cores ──────────────────────────────────────────────────────────────────
  static const _teal   = Color(0xFF27D3BE);
  static const _amber  = Color(0xFFFFB454);
  static const _red    = Color(0xFFFF6B6B);
  static const _surface= Color(0xFF102A32);

  @override
  void initState() {
    super.initState();
    _carregar();
  }

  Future<void> _carregar() async {
    setState(() { _loading = true; _erro = null; });
    try {
      final data = await FuncionarioSstService.meusAfastamentos();
      if (!mounted) return;
      setState(() => _lista = (data['afastamentos'] as List? ?? []));
    } catch (e) {
      if (!mounted) return;
      setState(() => _erro = e.toString().replaceFirst('Exception: ', ''));
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  _StatusInfo _info(String status) {
    switch (status) {
      case 'ativo':
        return _StatusInfo('Em afastamento', _amber, Icons.pause_circle_outline);
      case 'retorno_programado':
        return _StatusInfo('Retorno programado', _teal, Icons.event_available_outlined);
      case 'encerrado':
      default:
        return _StatusInfo('Encerrado', Colors.white38, Icons.check_circle_outline);
    }
  }

  Color _motivoColor(String motivo) {
    switch (motivo) {
      case 'acidente_trabalho':  return _red;
      case 'doenca_ocupacional': return _amber;
      case 'doenca_comum':       return Colors.blueAccent;
      default:                   return Colors.white38;
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      floatingActionButton: FloatingActionButton.small(
        onPressed: _carregar,
        tooltip: 'Atualizar',
        child: const Icon(Icons.refresh),
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
              Text(_erro!, textAlign: TextAlign.center,
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

    if (_lista.isEmpty) {
      return const Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.work_off_outlined, size: 56, color: Colors.white24),
            SizedBox(height: 12),
            Text('Nenhum afastamento registrado.',
                style: TextStyle(color: Colors.white38, fontSize: 15),
                textAlign: TextAlign.center),
            SizedBox(height: 6),
            Text('Seus afastamentos aparecerão aqui quando forem lançados.',
                style: TextStyle(color: Colors.white24, fontSize: 12),
                textAlign: TextAlign.center),
          ],
        ),
      );
    }

    return RefreshIndicator(
      onRefresh: _carregar,
      child: ListView.separated(
        padding: const EdgeInsets.fromLTRB(16, 12, 16, 80),
        itemCount: _lista.length,
        separatorBuilder: (_, __) => const SizedBox(height: 10),
        itemBuilder: (_, i) => _AfastamentoCard(
          item: _lista[i] as Map<String, dynamic>,
          statusInfo: _info((_lista[i] as Map)['status']?.toString() ?? ''),
          motivoColor: _motivoColor((_lista[i] as Map)['motivo']?.toString() ?? ''),
          surface: _surface,
        ),
      ),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
class _StatusInfo {
  const _StatusInfo(this.label, this.color, this.icon);
  final String  label;
  final Color   color;
  final IconData icon;
}

// ─────────────────────────────────────────────────────────────────────────────
class _AfastamentoCard extends StatelessWidget {
  const _AfastamentoCard({
    required this.item,
    required this.statusInfo,
    required this.motivoColor,
    required this.surface,
  });

  final Map<String, dynamic> item;
  final _StatusInfo statusInfo;
  final Color motivoColor;
  final Color surface;

  @override
  Widget build(BuildContext context) {
    final motivo    = item['motivo_label']?.toString() ?? '';
    final cid       = item['cid']?.toString() ?? '';
    final inicio    = item['data_inicio']?.toString() ?? '';
    final previsto  = item['data_prevista_retorno']?.toString();
    final retornou  = item['data_retorno_real']?.toString();
    final obs       = item['observacoes']?.toString() ?? '';
    final status    = item['status']?.toString() ?? '';

    return Container(
      decoration: BoxDecoration(
        color: surface,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: statusInfo.color.withValues(alpha: 0.25),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // ── Cabeçalho ─────────────────────────────────────────────────────
          Container(
            padding: const EdgeInsets.fromLTRB(14, 12, 14, 12),
            decoration: BoxDecoration(
              color: motivoColor.withValues(alpha: 0.10),
              borderRadius:
                  const BorderRadius.vertical(top: Radius.circular(16)),
            ),
            child: Row(
              children: [
                Icon(Icons.medical_services_outlined,
                    color: motivoColor, size: 18),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(motivo,
                      style: const TextStyle(
                          fontWeight: FontWeight.w700,
                          fontSize: 14,
                          color: Colors.white)),
                ),
                _StatusChip(info: statusInfo),
              ],
            ),
          ),

          // ── Detalhes ──────────────────────────────────────────────────────
          Padding(
            padding: const EdgeInsets.all(14),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                if (cid.isNotEmpty)
                  _Row(icon: Icons.local_hospital_outlined,
                      label: 'CID', value: cid),
                const SizedBox(height: 6),
                _Row(icon: Icons.calendar_today_outlined,
                    label: 'Início', value: inicio),
                if (previsto != null && previsto.isNotEmpty) ...[
                  const SizedBox(height: 6),
                  _Row(
                    icon: Icons.event_available_outlined,
                    label: 'Retorno previsto',
                    value: previsto,
                    valueColor: const Color(0xFF27D3BE),
                  ),
                ],
                if (retornou != null && retornou.isNotEmpty) ...[
                  const SizedBox(height: 6),
                  _Row(
                    icon: Icons.check_circle_outline,
                    label: 'Retornou em',
                    value: retornou,
                    valueColor: const Color(0xFF4CAF50),
                  ),
                ],
                if (obs.isNotEmpty) ...[
                  const SizedBox(height: 10),
                  const Divider(height: 1, color: Colors.white12),
                  const SizedBox(height: 10),
                  Text(obs,
                      style: const TextStyle(
                          color: Colors.white54, fontSize: 12, height: 1.4)),
                ],
                // Badge ativo pulsante (visual)
                if (status == 'ativo') ...[
                  const SizedBox(height: 12),
                  Container(
                    padding:
                        const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
                    decoration: BoxDecoration(
                      color: const Color(0xFFFFB454).withValues(alpha: 0.15),
                      borderRadius: BorderRadius.circular(8),
                      border: Border.all(
                          color: const Color(0xFFFFB454).withValues(alpha: 0.4)),
                    ),
                    child: const Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(Icons.info_outline,
                            size: 13, color: Color(0xFFFFB454)),
                        SizedBox(width: 5),
                        Text(
                          'Afastamento em curso — procure o RH para dúvidas',
                          style: TextStyle(
                              color: Color(0xFFFFB454),
                              fontSize: 11,
                              fontWeight: FontWeight.w600),
                        ),
                      ],
                    ),
                  ),
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
  const _StatusChip({required this.info});
  final _StatusInfo info;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: info.color.withValues(alpha: 0.18),
        borderRadius: BorderRadius.circular(999),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(info.icon, color: info.color, size: 12),
          const SizedBox(width: 4),
          Text(info.label,
              style: TextStyle(
                  color: info.color,
                  fontSize: 11,
                  fontWeight: FontWeight.w700)),
        ],
      ),
    );
  }
}

class _Row extends StatelessWidget {
  const _Row({
    required this.icon,
    required this.label,
    required this.value,
    this.valueColor,
  });
  final IconData icon;
  final String   label;
  final String   value;
  final Color?   valueColor;

  @override
  Widget build(BuildContext context) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Icon(icon, size: 14, color: Colors.white38),
        const SizedBox(width: 6),
        SizedBox(
            width: 96,
            child: Text(label,
                style:
                    const TextStyle(color: Colors.white38, fontSize: 12))),
        Expanded(
          child: Text(value,
              style: TextStyle(
                  color: valueColor ?? Colors.white70,
                  fontSize: 13,
                  fontWeight: FontWeight.w500)),
        ),
      ],
    );
  }
}
