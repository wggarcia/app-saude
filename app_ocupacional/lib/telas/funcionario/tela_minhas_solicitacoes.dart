import 'package:flutter/material.dart';

import '../../servicos/funcionario_sst_service.dart';

class TelaMinhasSolicitacoes extends StatefulWidget {
  const TelaMinhasSolicitacoes({super.key});

  @override
  State<TelaMinhasSolicitacoes> createState() => _TelaMinhasSolicitacoesState();
}

class _TelaMinhasSolicitacoesState extends State<TelaMinhasSolicitacoes> {
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
      final data = await FuncionarioSstService.solicitacoes();
      if (!mounted) return;
      setState(() => _lista = (data['solicitacoes'] as List<dynamic>? ?? []));
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
      return const Center(child: Text('Nenhuma solicitação encontrada.'));
    }

    return RefreshIndicator(
      onRefresh: _carregar,
      child: ListView.builder(
        padding: const EdgeInsets.all(12),
        itemCount: _lista.length,
        itemBuilder: (_, i) {
          final item = _lista[i] as Map<String, dynamic>;
          final clinica = (item['clinica_nome'] ?? item['destino'] ?? 'Operação interna').toString();
          final data = (item['data_agendamento'] ?? item['data_solicitacao'] ?? '-').toString();
          return Card(
            child: ListTile(
              leading: const Icon(Icons.medical_services_outlined),
              title: Text((item['tipo_aso_display'] ?? item['tipo_aso'] ?? 'Solicitação').toString()),
              subtitle: Text('$clinica • $data'),
              trailing: Text((item['status_display'] ?? item['status'] ?? '-').toString()),
              isThreeLine: false,
            ),
          );
        },
      ),
    );
  }
}
