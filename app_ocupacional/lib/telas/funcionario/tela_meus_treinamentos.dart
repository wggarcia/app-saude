import 'package:flutter/material.dart';

import '../../servicos/funcionario_sst_service.dart';

class TelaMeusTreinamentos extends StatefulWidget {
  const TelaMeusTreinamentos({super.key});

  @override
  State<TelaMeusTreinamentos> createState() => _TelaMeusTreinamentosState();
}

class _TelaMeusTreinamentosState extends State<TelaMeusTreinamentos> {
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
      final data = await FuncionarioSstService.treinamentos();
      if (!mounted) return;
      final lista = List<Map<String, dynamic>>.from(
        (data['treinamentos'] as List<dynamic>? ?? [])
            .map((e) => e as Map<String, dynamic>),
      );
      // Ordena: vencidos → a vencer → válidos
      lista.sort((a, b) => _prioridade(a).compareTo(_prioridade(b)));
      setState(() => _lista = lista);
    } catch (e) {
      if (!mounted) return;
      setState(() => _erro = e.toString().replaceFirst('Exception: ', ''));
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  int _prioridade(Map<String, dynamic> t) {
    final info = _statusInfo(t);
    if (info.label == 'Vencido') return 0;
    if (info.label == 'A vencer') return 1;
    return 2;
  }

  _TreinamentoStatus _statusInfo(Map<String, dynamic> t) {
    final vencStr = (t['data_vencimento'] ?? '').toString();
    if (vencStr.isEmpty || vencStr == '-' || vencStr == 'null') {
      return _TreinamentoStatus(label: 'Sem data', color: Colors.white38, icon: Icons.help_outline);
    }
    try {
      final venc = DateTime.parse(vencStr);
      final dias = venc.difference(DateTime.now()).inDays;
      if (dias < 0) {
        return _TreinamentoStatus(
          label: 'Vencido',
          color: const Color(0xFFFF6B6B),
          icon: Icons.warning_amber_outlined,
          dias: dias,
        );
      }
      if (dias <= 30) {
        return _TreinamentoStatus(
          label: 'A vencer',
          color: const Color(0xFFFFB454),
          icon: Icons.timer_outlined,
          dias: dias,
        );
      }
      return _TreinamentoStatus(
        label: 'Válido',
        color: const Color(0xFF27D3BE),
        icon: Icons.check_circle_outline,
        dias: dias,
      );
    } catch (_) {
      return _TreinamentoStatus(label: 'Sem data', color: Colors.white38, icon: Icons.help_outline);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Meus Treinamentos'),
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
            Icon(Icons.school_outlined, size: 56, color: Colors.white24),
            SizedBox(height: 12),
            Text('Nenhum treinamento registrado.',
              style: TextStyle(color: Colors.white38, fontSize: 16)),
          ],
        ),
      );
    }

    // Contadores para o resumo no topo
    final vencidos = _lista.where((t) => _statusInfo(t as Map<String, dynamic>).label == 'Vencido').length;
    final aVencer = _lista.where((t) => _statusInfo(t as Map<String, dynamic>).label == 'A vencer').length;
    final validos = _lista.where((t) => _statusInfo(t as Map<String, dynamic>).label == 'Válido').length;

    return RefreshIndicator(
      onRefresh: _carregar,
      child: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          // ── Resumo rápido ──
          Row(
            children: [
              _CountChip(count: vencidos, label: 'Vencidos', color: const Color(0xFFFF6B6B)),
              const SizedBox(width: 8),
              _CountChip(count: aVencer, label: 'A vencer', color: const Color(0xFFFFB454)),
              const SizedBox(width: 8),
              _CountChip(count: validos, label: 'Válidos', color: const Color(0xFF27D3BE)),
            ],
          ),
          const SizedBox(height: 16),
          ..._lista.map((item) {
            final t = item as Map<String, dynamic>;
            final status = _statusInfo(t);
            return Padding(
              padding: const EdgeInsets.only(bottom: 10),
              child: _TreinamentoCard(treinamento: t, status: status),
            );
          }),
        ],
      ),
    );
  }
}

class _TreinamentoStatus {
  const _TreinamentoStatus({
    required this.label,
    required this.color,
    required this.icon,
    this.dias = 0,
  });
  final String label;
  final Color color;
  final IconData icon;
  final int dias;
}

class _TreinamentoCard extends StatelessWidget {
  const _TreinamentoCard({required this.treinamento, required this.status});
  final Map<String, dynamic> treinamento;
  final _TreinamentoStatus status;

  @override
  Widget build(BuildContext context) {
    final titulo = (treinamento['titulo'] ?? 'Treinamento').toString();
    final nr = (treinamento['nr'] ?? '').toString();
    final cargaHoraria = (treinamento['carga_horaria'] ?? '').toString();
    final vencimento = (treinamento['data_vencimento'] ?? '-').toString();
    final realizacao = (treinamento['data_realizacao'] ?? treinamento['data_conclusao'] ?? '').toString();
    final instrutor = (treinamento['instrutor'] ?? '').toString();

    return Container(
      decoration: BoxDecoration(
        color: const Color(0xFF102A32),
        borderRadius: BorderRadius.circular(16),
        border: Border(
          left: BorderSide(color: status.color, width: 4),
        ),
      ),
      child: Padding(
        padding: const EdgeInsets.fromLTRB(14, 14, 14, 14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Expanded(
                  child: Text(
                    titulo,
                    style: const TextStyle(
                      fontWeight: FontWeight.w700,
                      fontSize: 14,
                      color: Colors.white,
                    ),
                  ),
                ),
                const SizedBox(width: 8),
                _StatusBadge(status: status),
              ],
            ),
            const SizedBox(height: 10),
            Wrap(
              spacing: 6,
              runSpacing: 6,
              children: [
                if (nr.isNotEmpty && nr != 'null')
                  _Tag(label: 'NR $nr', color: const Color(0xFF1E4D6B)),
                if (cargaHoraria.isNotEmpty && cargaHoraria != 'null')
                  _Tag(label: '$cargaHoraria h', color: const Color(0xFF1A3A2E)),
              ],
            ),
            const SizedBox(height: 10),
            if (realizacao.isNotEmpty && realizacao != 'null') ...[
              _InfoRow(icon: Icons.event_outlined, label: 'Realização', value: realizacao),
              const SizedBox(height: 5),
            ],
            _InfoRow(
              icon: Icons.event_available_outlined,
              label: 'Vencimento',
              value: vencimento,
              valueColor: status.label == 'Vencido'
                  ? const Color(0xFFFF6B6B)
                  : status.label == 'A vencer'
                      ? const Color(0xFFFFB454)
                      : null,
            ),
            if (status.label == 'Vencido') ...[
              const SizedBox(height: 4),
              Text(
                '  Vencido há ${status.dias.abs()} dias — solicite renovação',
                style: const TextStyle(fontSize: 11, color: Color(0xFFFF6B6B)),
              ),
            ] else if (status.label == 'A vencer') ...[
              const SizedBox(height: 4),
              Text(
                '  Vence em ${status.dias} dias',
                style: const TextStyle(fontSize: 11, color: Color(0xFFFFB454)),
              ),
            ],
            if (instrutor.isNotEmpty && instrutor != 'null') ...[
              const SizedBox(height: 5),
              _InfoRow(icon: Icons.person_outline, label: 'Instrutor', value: instrutor),
            ],
          ],
        ),
      ),
    );
  }
}

class _StatusBadge extends StatelessWidget {
  const _StatusBadge({required this.status});
  final _TreinamentoStatus status;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: status.color.withValues(alpha: 0.15),
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: status.color.withValues(alpha: 0.5)),
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

class _Tag extends StatelessWidget {
  const _Tag({required this.label, required this.color});
  final String label;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
      decoration: BoxDecoration(
        color: color,
        borderRadius: BorderRadius.circular(6),
      ),
      child: Text(label, style: const TextStyle(color: Colors.white, fontSize: 11, fontWeight: FontWeight.w600)),
    );
  }
}

class _CountChip extends StatelessWidget {
  const _CountChip({required this.count, required this.label, required this.color});
  final int count;
  final String label;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Expanded(
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 10),
        decoration: BoxDecoration(
          color: color.withValues(alpha: 0.12),
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: color.withValues(alpha: 0.3)),
        ),
        child: Column(
          children: [
            Text('$count',
              style: TextStyle(color: color, fontSize: 22, fontWeight: FontWeight.w900)),
            Text(label, style: TextStyle(color: color.withValues(alpha: 0.8), fontSize: 11)),
          ],
        ),
      ),
    );
  }
}

class _InfoRow extends StatelessWidget {
  const _InfoRow({required this.icon, required this.label, required this.value, this.valueColor});
  final IconData icon;
  final String label;
  final String value;
  final Color? valueColor;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Icon(icon, size: 14, color: Colors.white38),
        const SizedBox(width: 5),
        SizedBox(width: 72, child: Text(label, style: const TextStyle(color: Colors.white38, fontSize: 12))),
        Expanded(
          child: Text(value,
            style: TextStyle(
              color: valueColor ?? Colors.white70,
              fontSize: 13,
              fontWeight: FontWeight.w600,
            )),
        ),
      ],
    );
  }
}
