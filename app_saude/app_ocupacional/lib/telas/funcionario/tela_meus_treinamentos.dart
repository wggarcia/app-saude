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
      setState(() => _lista = (data['treinamentos'] as List<dynamic>? ?? []));
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
    if (_lista.isEmpty) {
      return const Center(child: Text('Nenhum treinamento encontrado.'));
    }

    return RefreshIndicator(
      onRefresh: _carregar,
      child: ListView.builder(
        itemCount: _lista.length,
        itemBuilder: (_, i) {
          final t = _lista[i] as Map<String, dynamic>;
          return Card(
            child: ListTile(
              title: Text((t['titulo'] ?? 'Treinamento').toString()),
              subtitle: Text(
                'NR ${t['nr'] ?? '-'} • Venc.: ${t['data_vencimento'] ?? '-'}',
              ),
            ),
          );
        },
      ),
    );
  }
}
