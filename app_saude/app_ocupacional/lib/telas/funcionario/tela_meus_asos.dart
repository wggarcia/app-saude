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
      final itens = (data['asos'] as List<dynamic>? ?? []);
      if (!mounted) return;
      setState(() => _lista = itens);
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
      return const Center(child: Text('Nenhum ASO encontrado.'));
    }

    return RefreshIndicator(
      onRefresh: _carregar,
      child: ListView.builder(
        itemCount: _lista.length,
        itemBuilder: (_, i) {
          final aso = _lista[i] as Map<String, dynamic>;
          return Card(
            child: ListTile(
              title: Text((aso['tipo_display'] ?? 'ASO').toString()),
              subtitle: Text(
                'Emissão: ${aso['data_emissao'] ?? '-'} • Validade: ${aso['data_validade'] ?? '-'}',
              ),
              trailing: Text((aso['resultado_display'] ?? '-').toString()),
            ),
          );
        },
      ),
    );
  }
}
