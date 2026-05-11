import 'package:flutter/material.dart';
import '../../servicos/empresa_auth_service.dart';
import '../../servicos/sst_service.dart';
import 'tela_login_empresa.dart';

class TelaAsosSST extends StatefulWidget {
  const TelaAsosSST({super.key});

  @override
  State<TelaAsosSST> createState() => _TelaAsosSSTState();
}

class _TelaAsosSSTState extends State<TelaAsosSST>
    with SingleTickerProviderStateMixin {
  static const _bg = Color(0xFF04131F);
  static const _accent = Color(0xFF39D0C3);

  late TabController _tabCtrl;

  List<dynamic> _asos = [];
  List<dynamic> _cats = [];
  bool _loadingAsos = true;
  bool _loadingCats = true;
  String? _erroAsos;
  String? _erroCats;

  @override
  void initState() {
    super.initState();
    _tabCtrl = TabController(length: 2, vsync: this);
    _loadAsos();
    _loadCats();
  }

  @override
  void dispose() {
    _tabCtrl.dispose();
    super.dispose();
  }

  Future<void> _loadAsos() async {
    setState(() {
      _loadingAsos = true;
      _erroAsos = null;
    });
    try {
      final data = await SSTService.getAsos();
      if (!mounted) return;
      setState(() {
        _asos = data is List ? data : (data['asos'] ?? []) as List;
        _loadingAsos = false;
      });
    } catch (e) {
      if (!mounted) return;
      final msg = e.toString().replaceFirst('Exception: ', '');
      if (msg.contains('expirada') || msg.contains('autenticado')) {
        await _handleUnauth();
        return;
      }
      setState(() {
        _erroAsos = msg;
        _loadingAsos = false;
      });
    }
  }

  Future<void> _loadCats() async {
    setState(() {
      _loadingCats = true;
      _erroCats = null;
    });
    try {
      final data = await SSTService.getCats();
      if (!mounted) return;
      setState(() {
        _cats = data is List ? data : (data['cats'] ?? []) as List;
        _loadingCats = false;
      });
    } catch (e) {
      if (!mounted) return;
      final msg = e.toString().replaceFirst('Exception: ', '');
      if (msg.contains('expirada') || msg.contains('autenticado')) {
        await _handleUnauth();
        return;
      }
      setState(() {
        _erroCats = msg;
        _loadingCats = false;
      });
    }
  }

  Future<void> _handleUnauth() async {
    await EmpresaAuthService.logout();
    if (!mounted) return;
    Navigator.of(context).pushAndRemoveUntil(
      MaterialPageRoute(builder: (_) => const TelaLoginEmpresa()),
      (_) => false,
    );
  }

  Future<void> _refresh() async {
    await Future.wait([_loadAsos(), _loadCats()]);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: _bg,
      appBar: AppBar(
        backgroundColor: _bg,
        foregroundColor: Colors.white,
        title: const Text(
          'ASO / CAT',
          style: TextStyle(fontSize: 18, fontWeight: FontWeight.w800),
        ),
        bottom: TabBar(
          controller: _tabCtrl,
          indicatorColor: _accent,
          labelColor: _accent,
          unselectedLabelColor: Colors.white54,
          tabs: const [
            Tab(text: 'ASO'),
            Tab(text: 'CAT'),
          ],
        ),
      ),
      body: RefreshIndicator(
        color: _accent,
        backgroundColor: const Color(0xFF0B2333),
        onRefresh: _refresh,
        child: TabBarView(
          controller: _tabCtrl,
          children: [
            _AsoTab(
              asos: _asos,
              loading: _loadingAsos,
              erro: _erroAsos,
              onRetry: _loadAsos,
            ),
            _CatTab(
              cats: _cats,
              loading: _loadingCats,
              erro: _erroCats,
              onRetry: _loadCats,
            ),
          ],
        ),
      ),
    );
  }
}

// ──────────────── ASO Tab ────────────────

class _AsoTab extends StatelessWidget {
  const _AsoTab({
    required this.asos,
    required this.loading,
    required this.erro,
    required this.onRetry,
  });

  final List<dynamic> asos;
  final bool loading;
  final String? erro;
  final VoidCallback onRetry;

  static const _accent = Color(0xFF39D0C3);

  @override
  Widget build(BuildContext context) {
    if (loading) {
      return const Center(
          child: CircularProgressIndicator(color: _accent));
    }
    if (erro != null) {
      return _ErrorView(erro: erro!, onRetry: onRetry);
    }
    if (asos.isEmpty) {
      return const Center(
        child: Text('Nenhum ASO encontrado.',
            style: TextStyle(color: Color(0xFF9CC4DB))),
      );
    }
    return ListView.separated(
      padding: const EdgeInsets.all(16),
      physics: const AlwaysScrollableScrollPhysics(),
      itemCount: asos.length,
      separatorBuilder: (_, __) => const SizedBox(height: 10),
      itemBuilder: (ctx, i) {
        final aso = asos[i] as Map<String, dynamic>;
        return _AsoCard(aso: aso);
      },
    );
  }
}

class _AsoCard extends StatelessWidget {
  const _AsoCard({required this.aso});

  final Map<String, dynamic> aso;

  static Color _statusColor(String status) {
    switch (status.toLowerCase()) {
      case 'vencido':
        return const Color(0xFFFF6B6B);
      case 'a_vencer':
      case 'vencendo':
        return const Color(0xFFFFD166);
      default:
        return const Color(0xFF4CAF50);
    }
  }

  static String _statusLabel(String status) {
    switch (status.toLowerCase()) {
      case 'vencido':
        return 'Vencido';
      case 'a_vencer':
      case 'vencendo':
        return 'A Vencer';
      default:
        return 'Vigente';
    }
  }

  @override
  Widget build(BuildContext context) {
    final nome = aso['funcionario']?.toString() ??
        aso['nome_funcionario']?.toString() ??
        '--';
    final tipo = aso['tipo']?.toString() ?? '--';
    final data = aso['data']?.toString() ??
        aso['data_realizacao']?.toString() ??
        '--';
    final validade = aso['validade']?.toString() ??
        aso['data_validade']?.toString() ??
        '--';
    final statusRaw = aso['status']?.toString() ?? 'vigente';
    final cor = _statusColor(statusRaw);
    final label = _statusLabel(statusRaw);
    final isAlerta = statusRaw.toLowerCase() == 'a_vencer' ||
        statusRaw.toLowerCase() == 'vencendo' ||
        statusRaw.toLowerCase() == 'vencido';

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: isAlerta
            ? cor.withValues(alpha: 0.07)
            : const Color(0xFF0B2333),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: isAlerta
              ? cor.withValues(alpha: 0.4)
              : const Color(0xFF39D0C3).withValues(alpha: 0.12),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(nome,
                    style: const TextStyle(
                        color: Colors.white,
                        fontWeight: FontWeight.w700)),
              ),
              _StatusBadge(label: label, color: cor),
            ],
          ),
          const SizedBox(height: 8),
          Wrap(
            spacing: 12,
            runSpacing: 6,
            children: [
              _InfoChipSimple(
                  icon: Icons.medical_services_outlined,
                  label: 'Tipo: $tipo'),
              _InfoChipSimple(
                  icon: Icons.calendar_today_outlined,
                  label: 'Data: $data'),
              _InfoChipSimple(
                  icon: Icons.event_outlined,
                  label: 'Validade: $validade'),
            ],
          ),
        ],
      ),
    );
  }
}

// ──────────────── CAT Tab ────────────────

class _CatTab extends StatelessWidget {
  const _CatTab({
    required this.cats,
    required this.loading,
    required this.erro,
    required this.onRetry,
  });

  final List<dynamic> cats;
  final bool loading;
  final String? erro;
  final VoidCallback onRetry;

  static const _accent = Color(0xFF39D0C3);

  @override
  Widget build(BuildContext context) {
    if (loading) {
      return const Center(
          child: CircularProgressIndicator(color: _accent));
    }
    if (erro != null) {
      return _ErrorView(erro: erro!, onRetry: onRetry);
    }
    if (cats.isEmpty) {
      return const Center(
        child: Text('Nenhuma CAT encontrada.',
            style: TextStyle(color: Color(0xFF9CC4DB))),
      );
    }
    return ListView.separated(
      padding: const EdgeInsets.all(16),
      physics: const AlwaysScrollableScrollPhysics(),
      itemCount: cats.length,
      separatorBuilder: (_, __) => const SizedBox(height: 10),
      itemBuilder: (ctx, i) {
        final cat = cats[i] as Map<String, dynamic>;
        return _CatCard(cat: cat);
      },
    );
  }
}

class _CatCard extends StatelessWidget {
  const _CatCard({required this.cat});

  final Map<String, dynamic> cat;

  static Color _gravidadeColor(String g) {
    switch (g.toLowerCase()) {
      case 'fatal':
      case 'grave':
        return const Color(0xFFFF6B6B);
      case 'moderado':
        return const Color(0xFFFFD166);
      default:
        return const Color(0xFF4CAF50);
    }
  }

  @override
  Widget build(BuildContext context) {
    final nome = cat['funcionario']?.toString() ??
        cat['nome_funcionario']?.toString() ??
        '--';
    final tipo = cat['tipo']?.toString() ?? '--';
    final data = cat['data']?.toString() ??
        cat['data_acidente']?.toString() ??
        '--';
    final gravidade = cat['gravidade']?.toString() ?? 'leve';
    final cid = cat['cid']?.toString() ?? '--';
    final statusEsocial =
        cat['status_esocial']?.toString() ?? '--';
    final gravidadeColor = _gravidadeColor(gravidade);

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0xFF0B2333),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: const Color(0xFF39D0C3).withValues(alpha: 0.12),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(nome,
                    style: const TextStyle(
                        color: Colors.white,
                        fontWeight: FontWeight.w700)),
              ),
              _StatusBadge(
                label: gravidade,
                color: gravidadeColor,
              ),
            ],
          ),
          const SizedBox(height: 8),
          Wrap(
            spacing: 12,
            runSpacing: 6,
            children: [
              _InfoChipSimple(
                  icon: Icons.assignment_outlined,
                  label: 'Tipo: $tipo'),
              _InfoChipSimple(
                  icon: Icons.calendar_today_outlined,
                  label: 'Data: $data'),
              _InfoChipSimple(
                  icon: Icons.local_hospital_outlined,
                  label: 'CID: $cid'),
              _InfoChipSimple(
                  icon: Icons.cloud_upload_outlined,
                  label: 'eSocial: $statusEsocial'),
            ],
          ),
        ],
      ),
    );
  }
}

// ──────────────── Shared Widgets ────────────────

class _StatusBadge extends StatelessWidget {
  const _StatusBadge({required this.label, required this.color});

  final String label;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding:
          const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.15),
        borderRadius: BorderRadius.circular(10),
        border:
            Border.all(color: color.withValues(alpha: 0.5)),
      ),
      child: Text(
        label,
        style: TextStyle(
          color: color,
          fontSize: 11,
          fontWeight: FontWeight.w700,
        ),
      ),
    );
  }
}

class _InfoChipSimple extends StatelessWidget {
  const _InfoChipSimple(
      {required this.icon, required this.label});

  final IconData icon;
  final String label;

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(icon, size: 13, color: const Color(0xFF9CC4DB)),
        const SizedBox(width: 4),
        Text(label,
            style: const TextStyle(
                color: Color(0xFF9CC4DB), fontSize: 12)),
      ],
    );
  }
}

class _ErrorView extends StatelessWidget {
  const _ErrorView({required this.erro, required this.onRetry});

  final String erro;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.wifi_off_outlined,
                color: Colors.white38, size: 48),
            const SizedBox(height: 16),
            Text(erro,
                textAlign: TextAlign.center,
                style:
                    const TextStyle(color: Color(0xFF9CC4DB))),
            const SizedBox(height: 20),
            FilledButton.icon(
              onPressed: onRetry,
              icon: const Icon(Icons.refresh),
              label: const Text('Tentar novamente'),
            ),
          ],
        ),
      ),
    );
  }
}
