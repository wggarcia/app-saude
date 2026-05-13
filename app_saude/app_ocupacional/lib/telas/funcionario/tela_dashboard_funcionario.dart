import 'package:flutter/material.dart';

import '../../servicos/funcionario_sst_service.dart';

class TelaDashboardFuncionario extends StatefulWidget {
  const TelaDashboardFuncionario({
    super.key,
    required this.nome,
    required this.cargo,
    required this.empresaNome,
  });

  final String nome;
  final String cargo;
  final String empresaNome;

  @override
  State<TelaDashboardFuncionario> createState() =>
      _TelaDashboardFuncionarioState();
}

class _TelaDashboardFuncionarioState extends State<TelaDashboardFuncionario> {
  Map<String, dynamic>? _dash;
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
      final data = await FuncionarioSstService.dashboard();
      if (!mounted) return;
      setState(() => _dash = data);
    } catch (e) {
      if (!mounted) return;
      setState(() => _erro = e.toString().replaceFirst('Exception: ', ''));
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) return const Center(child: CircularProgressIndicator());
    if (_erro != null) return Center(child: Text(_erro!));
    final d = _dash ?? {};
    return RefreshIndicator(
      onRefresh: _carregar,
      child: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          Text(widget.nome, style: Theme.of(context).textTheme.titleLarge),
          Text('${widget.cargo} • ${widget.empresaNome}'),
          const SizedBox(height: 16),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(12),
              child: Text(
                'Resumo operacional: ${(d['resumo'] ?? d).toString()}',
              ),
            ),
          ),
        ],
      ),
    );
  }
}
