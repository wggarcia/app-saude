import 'package:flutter/material.dart';
import '../../servicos/empresa_auth_service.dart';
import '../../servicos/sst_service.dart';
import 'tela_login_empresa.dart';

class TelaDashboardSST extends StatefulWidget {
  const TelaDashboardSST({super.key});

  @override
  State<TelaDashboardSST> createState() => _TelaDashboardSSTState();
}

class _TelaDashboardSSTState extends State<TelaDashboardSST> {
  static const _bg = Color(0xFF04131F);
  static const _card = Color(0xFF0B2333);
  static const _accent = Color(0xFF39D0C3);

  Map<String, dynamic>? _dashboard;
  Map<String, dynamic>? _empresa;
  bool _loading = true;
  String? _erro;

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
        SSTService.getDashboard(),
        EmpresaAuthService.getDadosEmpresa(),
      ]);
      if (!mounted) return;
      setState(() {
        _dashboard = results[0] as Map<String, dynamic>;
        _empresa = results[1] as Map<String, dynamic>;
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      final msg = e.toString().replaceFirst('Exception: ', '');
      if (msg.contains('expirada') || msg.contains('autenticado')) {
        await EmpresaAuthService.logout();
        if (!mounted) return;
        Navigator.of(context).pushAndRemoveUntil(
          MaterialPageRoute(builder: (_) => const TelaLoginEmpresa()),
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

  Future<void> _logout() async {
    final confirm = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: _card,
        title: const Text('Sair',
            style: TextStyle(color: Colors.white)),
        content: const Text(
          'Deseja encerrar a sessao empresarial?',
          style: TextStyle(color: Color(0xFF9CC4DB)),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('Cancelar'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            style: FilledButton.styleFrom(backgroundColor: const Color(0xFFFF6B6B)),
            child: const Text('Sair',
                style: TextStyle(color: Colors.white)),
          ),
        ],
      ),
    );
    if (confirm != true) return;
    await EmpresaAuthService.logout();
    if (!mounted) return;
    Navigator.of(context).pushAndRemoveUntil(
      MaterialPageRoute(builder: (_) => const TelaLoginEmpresa()),
      (_) => false,
    );
  }

  @override
  Widget build(BuildContext context) {
    final nomeEmpresa = _empresa?['nome']?.toString() ??
        _empresa?['razao_social']?.toString() ??
        'Empresa';

    return Scaffold(
      backgroundColor: _bg,
      body: RefreshIndicator(
        color: _accent,
        backgroundColor: _card,
        onRefresh: _load,
        child: CustomScrollView(
          physics: const AlwaysScrollableScrollPhysics(),
          slivers: [
            SliverAppBar(
              pinned: true,
              backgroundColor: _bg,
              foregroundColor: Colors.white,
              title: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    'Dashboard SST',
                    style: TextStyle(
                        fontSize: 18, fontWeight: FontWeight.w800),
                  ),
                  if (_empresa != null)
                    Text(
                      nomeEmpresa,
                      style: const TextStyle(
                        fontSize: 12,
                        color: _accent,
                        fontWeight: FontWeight.w500,
                      ),
                    ),
                ],
              ),
              actions: [
                IconButton(
                  icon: const Icon(Icons.logout_outlined),
                  tooltip: 'Sair',
                  onPressed: _logout,
                ),
              ],
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
                        Text(
                          _erro!,
                          textAlign: TextAlign.center,
                          style: const TextStyle(
                              color: Color(0xFF9CC4DB)),
                        ),
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
                padding: const EdgeInsets.fromLTRB(16, 8, 16, 28),
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
    final d = _dashboard ?? {};
    final kpis = d['kpis'] as Map<String, dynamic>? ?? {};
    final alertas =
        d['alertas_criticos'] as List<dynamic>? ?? [];

    final totalFuncionarios =
        kpis['total_funcionarios']?.toString() ?? '--';
    final asosVigentes =
        kpis['asos_vigentes']?.toString() ?? '--';
    final asosVencidos =
        kpis['asos_vencidos']?.toString() ?? '--';
    final cats = kpis['cats_registradas']?.toString() ?? '--';
    final score = kpis['score_compliance']?.toString() ?? '--';

    return [
      const SizedBox(height: 8),
      // KPI Grid
      GridView.count(
        crossAxisCount: 2,
        shrinkWrap: true,
        physics: const NeverScrollableScrollPhysics(),
        mainAxisSpacing: 12,
        crossAxisSpacing: 12,
        childAspectRatio: 1.55,
        children: [
          _KpiCard(
            label: 'Funcionarios',
            value: totalFuncionarios,
            icon: Icons.people,
            color: _accent,
          ),
          _KpiCard(
            label: 'ASOs Vigentes',
            value: asosVigentes,
            icon: Icons.check_circle_outline,
            color: const Color(0xFF4CAF50),
          ),
          _KpiCard(
            label: 'ASOs Vencidos',
            value: asosVencidos,
            icon: Icons.warning_amber_outlined,
            color: const Color(0xFFFF6B6B),
          ),
          _KpiCard(
            label: 'CATs Registradas',
            value: cats,
            icon: Icons.report_outlined,
            color: const Color(0xFFFFA657),
          ),
        ],
      ),
      const SizedBox(height: 12),
      // Score Compliance
      Container(
        padding: const EdgeInsets.all(18),
        decoration: BoxDecoration(
          gradient: const LinearGradient(
            colors: [Color(0xFF12324B), Color(0xFF0A1B29)],
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
          ),
          borderRadius: BorderRadius.circular(20),
          border: Border.all(
              color: _accent.withValues(alpha: 0.3)),
        ),
        child: Row(
          children: [
            Container(
              width: 52,
              height: 52,
              decoration: BoxDecoration(
                color: _accent.withValues(alpha: 0.15),
                borderRadius: BorderRadius.circular(16),
                border: Border.all(
                    color: _accent.withValues(alpha: 0.4)),
              ),
              child: const Center(
                child: Icon(Icons.shield_outlined,
                    color: _accent, size: 28),
              ),
            ),
            const SizedBox(width: 16),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    'Score de Compliance SST',
                    style: TextStyle(
                      color: Color(0xFF9CC4DB),
                      fontSize: 13,
                    ),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    score,
                    style: const TextStyle(
                      color: Colors.white,
                      fontSize: 28,
                      fontWeight: FontWeight.w900,
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
      const SizedBox(height: 20),
      // Alertas criticos
      if (alertas.isNotEmpty) ...[
        const Text(
          'Alertas Criticos — ASOs vencendo em 30 dias',
          style: TextStyle(
            color: Colors.white,
            fontSize: 16,
            fontWeight: FontWeight.w700,
          ),
        ),
        const SizedBox(height: 10),
        ...alertas.map((item) {
          final a = item as Map<String, dynamic>;
          return _AlertaCriticoCard(alerta: a);
        }),
      ] else ...[
        Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: const Color(0xFF0E2E1A),
            borderRadius: BorderRadius.circular(16),
            border: Border.all(
                color: const Color(0xFF4CAF50)
                    .withValues(alpha: 0.4)),
          ),
          child: const Row(
            children: [
              Icon(Icons.check_circle,
                  color: Color(0xFF4CAF50)),
              SizedBox(width: 12),
              Expanded(
                child: Text(
                  'Nenhum ASO vencendo nos proximos 30 dias.',
                  style: TextStyle(
                      color: Colors.white, height: 1.4),
                ),
              ),
            ],
          ),
        ),
      ],
    ];
  }
}

class _KpiCard extends StatelessWidget {
  const _KpiCard({
    required this.label,
    required this.value,
    required this.icon,
    required this.color,
  });

  final String label;
  final String value;
  final IconData icon;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: const Color(0xFF0B2333),
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: color.withValues(alpha: 0.25)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Icon(icon, color: color, size: 22),
          const Spacer(),
          Text(
            value,
            style: TextStyle(
              color: color,
              fontSize: 24,
              fontWeight: FontWeight.w900,
            ),
          ),
          const SizedBox(height: 2),
          Text(
            label,
            style: const TextStyle(
              color: Color(0xFF9CC4DB),
              fontSize: 12,
            ),
          ),
        ],
      ),
    );
  }
}

class _AlertaCriticoCard extends StatelessWidget {
  const _AlertaCriticoCard({required this.alerta});

  final Map<String, dynamic> alerta;

  @override
  Widget build(BuildContext context) {
    final nome = alerta['funcionario']?.toString() ??
        alerta['nome']?.toString() ??
        'Funcionario';
    final vencimento = alerta['vencimento']?.toString() ??
        alerta['data_validade']?.toString() ??
        '';
    final diasRestantes = alerta['dias_restantes'];

    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: const Color(0xFF2E1A0E),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: const Color(0xFFFF6B6B).withValues(alpha: 0.4),
        ),
      ),
      child: Row(
        children: [
          const Icon(Icons.warning_amber_rounded,
              color: Color(0xFFFFA657), size: 20),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  nome,
                  style: const TextStyle(
                    color: Colors.white,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                if (vencimento.isNotEmpty)
                  Text(
                    'Vencimento: $vencimento',
                    style: const TextStyle(
                      color: Color(0xFF9CC4DB),
                      fontSize: 12,
                    ),
                  ),
              ],
            ),
          ),
          if (diasRestantes != null)
            Container(
              padding: const EdgeInsets.symmetric(
                  horizontal: 10, vertical: 4),
              decoration: BoxDecoration(
                color: const Color(0xFF4A1C1C),
                borderRadius: BorderRadius.circular(10),
              ),
              child: Text(
                '$diasRestantes d',
                style: const TextStyle(
                  color: Color(0xFFFF6B6B),
                  fontWeight: FontWeight.w700,
                  fontSize: 12,
                ),
              ),
            ),
        ],
      ),
    );
  }
}
