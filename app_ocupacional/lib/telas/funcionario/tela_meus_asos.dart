import 'package:flutter/material.dart';

import '../../servicos/funcionario_sst_service.dart';

class TelaMeusAsos extends StatefulWidget {
  const TelaMeusAsos({super.key});

  @override
  State<TelaMeusAsos> createState() => _TelaMeusAsosState();
}

class _TelaMeusAsosState extends State<TelaMeusAsos> {
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
      final data = await FuncionarioSstService.asos();
      if (!mounted) return;
      setState(() => _lista = (data['asos'] as List<dynamic>? ?? []));
    } catch (e) {
      if (!mounted) return;
      setState(() => _erro = e.toString().replaceFirst('Exception: ', ''));
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  // Interpreta resultado/status de forma unificada
  _AsoInfo _info(Map<String, dynamic> aso) {
    final resultado = (aso['resultado'] ?? aso['resultado_display'] ?? '').toString().toLowerCase();
    final validadeStr = aso['data_validade']?.toString() ?? '';

    // Verifica se está vencido pela data
    bool vencido = false;
    int diasRestantes = 0;
    if (validadeStr.isNotEmpty && validadeStr != '-') {
      try {
        final validade = DateTime.parse(validadeStr);
        diasRestantes = validade.difference(DateTime.now()).inDays;
        vencido = diasRestantes < 0;
      } catch (_) {}
    }

    if (resultado.contains('inapt')) {
      return _AsoInfo(label: 'Inapto', color: const Color(0xFFFF6B6B), icon: Icons.cancel_outlined);
    }
    if (vencido) {
      return _AsoInfo(label: 'Vencido', color: const Color(0xFFFF6B6B), icon: Icons.warning_amber_outlined, diasRestantes: diasRestantes);
    }
    if (diasRestantes > 0 && diasRestantes <= 30) {
      return _AsoInfo(label: 'A vencer', color: const Color(0xFFFFB454), icon: Icons.timer_outlined, diasRestantes: diasRestantes);
    }
    if (resultado.contains('apt') || resultado.contains('ok') || diasRestantes > 0) {
      return _AsoInfo(label: 'Apto', color: const Color(0xFF27D3BE), icon: Icons.check_circle_outline, diasRestantes: diasRestantes);
    }
    return _AsoInfo(label: resultado.isEmpty ? 'Pendente' : resultado, color: Colors.white38, icon: Icons.hourglass_empty_outlined);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Meus ASOs'),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: _carregar,
            tooltip: 'Atualizar',
          ),
        ],
      ),
      body: _buildBody(context),
    );
  }

  Widget _buildBody(BuildContext context) {
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
            Icon(Icons.assignment_outlined, size: 56, color: Colors.white24),
            SizedBox(height: 12),
            Text('Nenhum ASO encontrado.',
              style: TextStyle(color: Colors.white38, fontSize: 16)),
            SizedBox(height: 6),
            Text('Seus documentos ocupacionais aparecerão aqui.',
              style: TextStyle(color: Colors.white24, fontSize: 13)),
          ],
        ),
      );
    }

    // Separa o mais recente dos demais
    final todos = List<Map<String, dynamic>>.from(_lista.map((e) => e as Map<String, dynamic>));
    final atual = todos.isNotEmpty ? todos.first : null;
    final historico = todos.length > 1 ? todos.sublist(1) : <Map<String, dynamic>>[];

    return RefreshIndicator(
      onRefresh: _carregar,
      child: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          if (atual != null) ...[
            const _SectionHeader(title: 'ASO ATUAL'),
            const SizedBox(height: 8),
            _AsoCard(aso: atual, info: _info(atual), destaque: true),
            const SizedBox(height: 20),
          ],
          if (historico.isNotEmpty) ...[
            const _SectionHeader(title: 'HISTÓRICO'),
            const SizedBox(height: 8),
            ...historico.map((aso) => Padding(
              padding: const EdgeInsets.only(bottom: 10),
              child: _AsoCard(aso: aso, info: _info(aso), destaque: false),
            )),
          ],
        ],
      ),
    );
  }
}

class _AsoInfo {
  const _AsoInfo({
    required this.label,
    required this.color,
    required this.icon,
    this.diasRestantes = 0,
  });
  final String label;
  final Color color;
  final IconData icon;
  final int diasRestantes;
}

class _AsoCard extends StatelessWidget {
  const _AsoCard({required this.aso, required this.info, required this.destaque});

  final Map<String, dynamic> aso;
  final _AsoInfo info;
  final bool destaque;

  @override
  Widget build(BuildContext context) {
    final tipo = (aso['tipo_display'] ?? aso['tipo'] ?? 'ASO').toString();
    final emissao = (aso['data_emissao'] ?? '-').toString();
    final validade = (aso['data_validade'] ?? '-').toString();
    final medico = (aso['medico_nome'] ?? aso['medico'] ?? '').toString();
    final clinica = (aso['clinica_nome'] ?? aso['clinica'] ?? '').toString();

    return Container(
      decoration: BoxDecoration(
        color: const Color(0xFF102A32),
        borderRadius: BorderRadius.circular(18),
        border: Border(
          left: BorderSide(color: info.color, width: 4),
        ),
        boxShadow: destaque
            ? [BoxShadow(color: info.color.withValues(alpha: 0.18), blurRadius: 18, offset: const Offset(0, 4))]
            : null,
      ),
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: Text(
                    tipo,
                    style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 16, color: Colors.white),
                  ),
                ),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
                  decoration: BoxDecoration(
                    color: info.color.withValues(alpha: 0.18),
                    borderRadius: BorderRadius.circular(999),
                    border: Border.all(color: info.color.withValues(alpha: 0.5)),
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(info.icon, color: info.color, size: 14),
                      const SizedBox(width: 5),
                      Text(info.label,
                        style: TextStyle(color: info.color, fontWeight: FontWeight.w700, fontSize: 12)),
                    ],
                  ),
                ),
              ],
            ),
            const SizedBox(height: 12),
            _InfoRow(icon: Icons.event_outlined, label: 'Emissão', value: emissao),
            const SizedBox(height: 6),
            _InfoRow(
              icon: Icons.event_available_outlined,
              label: 'Validade',
              value: validade,
              valueColor: info.diasRestantes < 0
                  ? const Color(0xFFFF6B6B)
                  : info.diasRestantes <= 30 && info.diasRestantes >= 0
                      ? const Color(0xFFFFB454)
                      : null,
            ),
            if (info.diasRestantes > 0) ...[
              const SizedBox(height: 4),
              Text(
                info.diasRestantes <= 30
                    ? '  ⚠ Vence em ${info.diasRestantes} dias'
                    : '  Válido por mais ${info.diasRestantes} dias',
                style: TextStyle(
                  fontSize: 12,
                  color: info.diasRestantes <= 30 ? const Color(0xFFFFB454) : Colors.white38,
                ),
              ),
            ],
            if (medico.isNotEmpty) ...[
              const SizedBox(height: 6),
              _InfoRow(icon: Icons.person_outline, label: 'Médico', value: medico),
            ],
            if (clinica.isNotEmpty) ...[
              const SizedBox(height: 6),
              _InfoRow(icon: Icons.local_hospital_outlined, label: 'Clínica', value: clinica),
            ],
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
        Icon(icon, size: 15, color: Colors.white38),
        const SizedBox(width: 6),
        SizedBox(
          width: 70,
          child: Text(label, style: const TextStyle(color: Colors.white38, fontSize: 12)),
        ),
        Expanded(
          child: Text(
            value,
            style: TextStyle(
              color: valueColor ?? Colors.white70,
              fontWeight: FontWeight.w600,
              fontSize: 13,
            ),
          ),
        ),
      ],
    );
  }
}

class _SectionHeader extends StatelessWidget {
  const _SectionHeader({required this.title});
  final String title;

  @override
  Widget build(BuildContext context) {
    return Text(
      title,
      style: const TextStyle(
        color: Color(0xFF27D3BE),
        fontSize: 11,
        fontWeight: FontWeight.w800,
        letterSpacing: 1.2,
      ),
    );
  }
}
