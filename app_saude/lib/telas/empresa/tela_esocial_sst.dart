import 'package:flutter/material.dart';
import '../../servicos/empresa_auth_service.dart';
import '../../servicos/sst_service.dart';
import 'tela_login_empresa.dart';

class TelaEsocialSST extends StatefulWidget {
  const TelaEsocialSST({super.key});

  @override
  State<TelaEsocialSST> createState() => _TelaEsocialSSTState();
}

class _TelaEsocialSSTState extends State<TelaEsocialSST> {
  static const _bg = Color(0xFF04131F);
  static const _accent = Color(0xFF39D0C3);

  Map<String, dynamic>? _kpis;
  List<dynamic> _eventos = [];
  bool _loading = true;
  String? _erro;
  final Set<int> _transmitindo = {};

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _erro = null;
    });
    try {
      final results = await Future.wait([
        SSTService.getEsocialKpis(),
        SSTService.getEsocialEventos(),
      ]);
      if (!mounted) return;
      setState(() {
        _kpis = results[0] as Map<String, dynamic>;
        final ev = results[1];
        _eventos = ev is List
            ? ev
            : (ev as Map<String, dynamic>)['eventos'] as List? ?? [];
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      final msg = e.toString().replaceFirst('Exception: ', '');
      if (msg.contains('expirada') || msg.contains('autenticado')) {
        await EmpresaAuthService.logout();
        if (!mounted) return;
        Navigator.of(context).pushAndRemoveUntil(
          MaterialPageRoute(
              builder: (_) => const TelaLoginEmpresa()),
          (_) => false,
        );
        return;
      }
      setState(() {
        _erro = msg;
        _loading = false;
      });
    }
  }

  Future<void> _transmitir(int id) async {
    setState(() => _transmitindo.add(id));
    try {
      await SSTService.transmitirEvento(id);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Evento transmitido com sucesso.'),
          backgroundColor: Color(0xFF4CAF50),
        ),
      );
      await _load();
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
              e.toString().replaceFirst('Exception: ', '')),
          backgroundColor: const Color(0xFFFF6B6B),
        ),
      );
    } finally {
      if (mounted) setState(() => _transmitindo.remove(id));
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: _bg,
      body: RefreshIndicator(
        color: _accent,
        backgroundColor: const Color(0xFF0B2333),
        onRefresh: _load,
        child: CustomScrollView(
          physics: const AlwaysScrollableScrollPhysics(),
          slivers: [
            const SliverAppBar(
              pinned: true,
              backgroundColor: _bg,
              foregroundColor: Colors.white,
              title: Text(
                'Monitor eSocial',
                style: TextStyle(
                    fontSize: 18, fontWeight: FontWeight.w800),
              ),
            ),
            if (_loading)
              const SliverFillRemaining(
                child: Center(
                  child: CircularProgressIndicator(color: _accent),
                ),
              )
            else if (_erro != null)
              SliverFillRemaining(
                child: Center(
                  child: Padding(
                    padding: const EdgeInsets.all(24),
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        const Icon(Icons.wifi_off_outlined,
                            color: Colors.white38, size: 48),
                        const SizedBox(height: 16),
                        Text(_erro!,
                            textAlign: TextAlign.center,
                            style: const TextStyle(
                                color: Color(0xFF9CC4DB))),
                        const SizedBox(height: 20),
                        FilledButton.icon(
                          onPressed: _load,
                          icon: const Icon(Icons.refresh),
                          label: const Text('Tentar novamente'),
                        ),
                      ],
                    ),
                  ),
                ),
              )
            else
              SliverPadding(
                padding:
                    const EdgeInsets.fromLTRB(16, 8, 16, 28),
                sliver: SliverList(
                  delegate: SliverChildListDelegate(
                    _buildContent(),
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }

  List<Widget> _buildContent() {
    final kpis = _kpis ?? {};
    final pendentes =
        kpis['pendentes']?.toString() ?? '--';
    final transmitidos =
        kpis['transmitidos']?.toString() ?? '--';
    final erros = kpis['erros']?.toString() ?? '--';

    // Agrupar eventos por tipo
    final Map<String, List<dynamic>> porTipo = {};
    for (final ev in _eventos) {
      final m = ev as Map<String, dynamic>;
      final tipo = m['tipo']?.toString() ?? 'Outro';
      porTipo.putIfAbsent(tipo, () => []).add(m);
    }

    final tiposOrdenados = [
      'S-2210',
      'S-2220',
      'S-2230',
      'S-2240',
      ...porTipo.keys.where((t) => !['S-2210', 'S-2220', 'S-2230', 'S-2240']
          .contains(t)),
    ].where((t) => porTipo.containsKey(t)).toList();

    return [
      // KPI Strip
      Row(
        children: [
          Expanded(
            child: _KpiStrip(
              label: 'Pendentes',
              value: pendentes,
              color: const Color(0xFFFFB830),
              icon: Icons.hourglass_empty_outlined,
            ),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: _KpiStrip(
              label: 'Transmitidos',
              value: transmitidos,
              color: const Color(0xFF4CAF50),
              icon: Icons.cloud_done_outlined,
            ),
          ),
          const SizedBox(width: 10),
          Expanded(
            child: _KpiStrip(
              label: 'Erros',
              value: erros,
              color: const Color(0xFFFF6B6B),
              icon: Icons.error_outline,
            ),
          ),
        ],
      ),
      const SizedBox(height: 20),
      if (_eventos.isEmpty)
        Container(
          padding: const EdgeInsets.all(20),
          decoration: BoxDecoration(
            color: const Color(0xFF0B2333),
            borderRadius: BorderRadius.circular(16),
          ),
          child: const Center(
            child: Text(
              'Nenhum evento eSocial encontrado.',
              style: TextStyle(color: Color(0xFF9CC4DB)),
            ),
          ),
        )
      else
        ...tiposOrdenados.map((tipo) {
          final lista = porTipo[tipo]!;
          return Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Padding(
                padding: const EdgeInsets.only(bottom: 8),
                child: Row(
                  children: [
                    Container(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 10, vertical: 4),
                      decoration: BoxDecoration(
                        color: const Color(0xFF39D0C3)
                            .withValues(alpha: 0.15),
                        borderRadius: BorderRadius.circular(8),
                      ),
                      child: Text(
                        tipo,
                        style: const TextStyle(
                          color: Color(0xFF39D0C3),
                          fontSize: 12,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                    ),
                    const SizedBox(width: 8),
                    Text(
                      '${lista.length} evento${lista.length == 1 ? '' : 's'}',
                      style: const TextStyle(
                        color: Colors.white54,
                        fontSize: 12,
                      ),
                    ),
                  ],
                ),
              ),
              ...lista.map((ev) {
                final m = ev as Map<String, dynamic>;
                return _EventoCard(
                  evento: m,
                  transmitindo:
                      _transmitindo.contains(m['id'] as int?),
                  onTransmitir: () {
                    final id = m['id'];
                    if (id != null) _transmitir(id as int);
                  },
                );
              }),
              const SizedBox(height: 12),
            ],
          );
        }),
    ];
  }
}

class _KpiStrip extends StatelessWidget {
  const _KpiStrip({
    required this.label,
    required this.value,
    required this.color,
    required this.icon,
  });

  final String label;
  final String value;
  final Color color;
  final IconData icon;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding:
          const EdgeInsets.symmetric(vertical: 14, horizontal: 12),
      decoration: BoxDecoration(
        color: const Color(0xFF0B2333),
        borderRadius: BorderRadius.circular(16),
        border:
            Border.all(color: color.withValues(alpha: 0.3)),
      ),
      child: Column(
        children: [
          Icon(icon, color: color, size: 20),
          const SizedBox(height: 6),
          Text(
            value,
            style: TextStyle(
              color: color,
              fontSize: 22,
              fontWeight: FontWeight.w900,
            ),
          ),
          const SizedBox(height: 2),
          Text(
            label,
            style: const TextStyle(
              color: Color(0xFF9CC4DB),
              fontSize: 11,
            ),
            textAlign: TextAlign.center,
          ),
        ],
      ),
    );
  }
}

class _EventoCard extends StatelessWidget {
  const _EventoCard({
    required this.evento,
    required this.transmitindo,
    required this.onTransmitir,
  });

  final Map<String, dynamic> evento;
  final bool transmitindo;
  final VoidCallback onTransmitir;

  static Color _statusColor(String s) {
    switch (s.toLowerCase()) {
      case 'transmitido':
        return const Color(0xFF4CAF50);
      case 'erro':
        return const Color(0xFFFF6B6B);
      default:
        return const Color(0xFFFFB830);
    }
  }

  static String _statusLabel(String s) {
    switch (s.toLowerCase()) {
      case 'transmitido':
        return 'Transmitido';
      case 'erro':
        return 'Erro';
      default:
        return 'Pendente';
    }
  }

  @override
  Widget build(BuildContext context) {
    final descricao = evento['descricao']?.toString() ??
        evento['titulo']?.toString() ??
        'Evento';
    final statusRaw =
        evento['status']?.toString() ?? 'pendente';
    final data = evento['data']?.toString() ?? '--';
    final cor = _statusColor(statusRaw);
    final label = _statusLabel(statusRaw);
    final isPendente = statusRaw.toLowerCase() == 'pendente';

    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: const Color(0xFF0B2333),
        borderRadius: BorderRadius.circular(14),
        border: Border.all(
            color: cor.withValues(alpha: 0.25)),
      ),
      child: Row(
        children: [
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Expanded(
                      child: Text(
                        descricao,
                        style: const TextStyle(
                          color: Colors.white,
                          fontWeight: FontWeight.w600,
                          fontSize: 13,
                        ),
                      ),
                    ),
                    Container(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 8, vertical: 3),
                      decoration: BoxDecoration(
                        color: cor.withValues(alpha: 0.15),
                        borderRadius: BorderRadius.circular(8),
                        border: Border.all(
                            color: cor.withValues(alpha: 0.5)),
                      ),
                      child: Text(
                        label,
                        style: TextStyle(
                          color: cor,
                          fontSize: 10,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 4),
                Text(
                  'Data: $data',
                  style: const TextStyle(
                    color: Color(0xFF9CC4DB),
                    fontSize: 12,
                  ),
                ),
              ],
            ),
          ),
          if (isPendente) ...[
            const SizedBox(width: 10),
            SizedBox(
              height: 32,
              child: transmitindo
                  ? const SizedBox(
                      width: 20,
                      height: 20,
                      child: CircularProgressIndicator(
                        strokeWidth: 2,
                        color: Color(0xFF39D0C3),
                      ),
                    )
                  : FilledButton(
                      onPressed: onTransmitir,
                      style: FilledButton.styleFrom(
                        backgroundColor:
                            const Color(0xFF39D0C3),
                        foregroundColor:
                            const Color(0xFF04131F),
                        padding: const EdgeInsets.symmetric(
                            horizontal: 12),
                        minimumSize: Size.zero,
                        tapTargetSize:
                            MaterialTapTargetSize.shrinkWrap,
                      ),
                      child: const Text(
                        'Transmitir',
                        style: TextStyle(
                          fontSize: 12,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                    ),
            ),
          ],
        ],
      ),
    );
  }
}
