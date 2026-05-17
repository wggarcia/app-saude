import 'package:flutter/material.dart';

import '../../servicos/empresa_auth_service.dart';
import '../../servicos/empresa_sst_service.dart';
import 'tela_login_empresa.dart';

class TelaDashboardEmpresa extends StatefulWidget {
  const TelaDashboardEmpresa({super.key, required this.empresaNome});

  final String empresaNome;

  @override
  State<TelaDashboardEmpresa> createState() => _TelaDashboardEmpresaState();
}

class _TelaDashboardEmpresaState extends State<TelaDashboardEmpresa> {
  Map<String, dynamic>? _dados;
  bool _loading = true;
  String? _erro;

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
      final dados = await EmpresaSstService.dashboard();
      if (!mounted) return;
      setState(() => _dados = dados);
    } catch (e) {
      if (!mounted) return;
      setState(() => _erro = e.toString().replaceFirst('Exception: ', ''));
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _sair() async {
    await EmpresaAuthService.logout();
    if (!mounted) return;
    Navigator.of(context).pushReplacement(
      MaterialPageRoute(builder: (_) => const TelaLoginEmpresa()),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text(widget.empresaNome),
        actions: [
          IconButton(
            tooltip: 'Sair',
            onPressed: _sair,
            icon: const Icon(Icons.logout),
          ),
        ],
      ),
      body: _body(context),
    );
  }

  Widget _body(BuildContext context) {
    if (_loading) return const Center(child: CircularProgressIndicator());
    if (_erro != null) {
      return _ErroState(mensagem: _erro!, onRetry: _carregar);
    }

    final dados = _dados ?? {};
    final asos = _map(dados['asos']);
    final exames = _map(dados['exames']);
    final esocial = _map(dados['esocial']);
    final afastamentos = _map(dados['afastamentos']);
    final alertas =
        dados['alertas'] is List ? dados['alertas'] as List : const [];

    return RefreshIndicator(
      onRefresh: _carregar,
      child: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Text(
            dados['empresa_nome']?.toString() ?? widget.empresaNome,
            style: Theme.of(
              context,
            ).textTheme.titleLarge?.copyWith(fontWeight: FontWeight.w800),
          ),
          const SizedBox(height: 16),
          LayoutBuilder(
            builder: (context, constraints) {
              final columns = constraints.maxWidth > 680 ? 3 : 2;
              return GridView.count(
                crossAxisCount: columns,
                mainAxisSpacing: 10,
                crossAxisSpacing: 10,
                childAspectRatio: columns == 3 ? 1.45 : 1.2,
                shrinkWrap: true,
                physics: const NeverScrollableScrollPhysics(),
                children: [
                  _KpiCard(
                    'Funcionários',
                    dados['funcionarios_ativos'],
                    Icons.groups_outlined,
                  ),
                  _KpiCard(
                    'ASOs vencidos',
                    asos['vencidos'],
                    Icons.assignment_late_outlined,
                  ),
                  _KpiCard(
                    'ASOs 60 dias',
                    asos['a_vencer_60d'],
                    Icons.event_available_outlined,
                  ),
                  _KpiCard(
                    'Exames atraso',
                    exames['atrasados'],
                    Icons.medical_services_outlined,
                  ),
                  _KpiCard(
                    'eSocial pend.',
                    esocial['pendentes'],
                    Icons.cloud_upload_outlined,
                  ),
                  _KpiCard(
                    'Absenteísmo',
                    '${afastamentos['absenteismo_pct'] ?? 0}%',
                    Icons.timeline_outlined,
                  ),
                ],
              );
            },
          ),
          const SizedBox(height: 16),
          Text(
            'Alertas SST',
            style: Theme.of(
              context,
            ).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w800),
          ),
          const SizedBox(height: 8),
          if (alertas.isEmpty)
            const Card(
              child: Padding(
                padding: EdgeInsets.all(16),
                child: Text('Nenhum alerta crítico no momento.'),
              ),
            )
          else
            ...alertas.map((alerta) {
              final item = alerta is Map ? alerta : const {};
              return Card(
                child: ListTile(
                  leading: Icon(
                    Icons.warning_amber_outlined,
                    color: _corAlerta(context, item['nivel']?.toString()),
                  ),
                  title: Text(item['mensagem']?.toString() ?? 'Alerta'),
                  subtitle: Text(
                    item['nivel']?.toString().toUpperCase() ?? 'ATENÇÃO',
                  ),
                ),
              );
            }),
        ],
      ),
    );
  }

  static Map<String, dynamic> _map(Object? value) {
    if (value is Map<String, dynamic>) return value;
    return {};
  }

  static Color _corAlerta(BuildContext context, String? nivel) {
    if (nivel == 'critico') return Theme.of(context).colorScheme.error;
    if (nivel == 'alto') return Theme.of(context).colorScheme.secondary;
    return Theme.of(context).colorScheme.primary;
  }
}

class _KpiCard extends StatelessWidget {
  const _KpiCard(this.label, this.value, this.icon);

  final String label;
  final Object? value;
  final IconData icon;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Icon(icon, color: Theme.of(context).colorScheme.primary),
            Text(
              value?.toString() ?? '0',
              style: Theme.of(
                context,
              ).textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.w800),
            ),
            Text(label, maxLines: 2, overflow: TextOverflow.ellipsis),
          ],
        ),
      ),
    );
  }
}

class _ErroState extends StatelessWidget {
  const _ErroState({required this.mensagem, required this.onRetry});

  final String mensagem;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.cloud_off_outlined, size: 44),
            const SizedBox(height: 12),
            Text(mensagem, textAlign: TextAlign.center),
            const SizedBox(height: 12),
            OutlinedButton.icon(
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
