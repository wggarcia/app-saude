import 'package:flutter/material.dart';

import '../../servicos/funcionario_sst_service.dart';

class TelaNotificacoes extends StatefulWidget {
  final VoidCallback? onLidas;
  const TelaNotificacoes({super.key, this.onLidas});

  @override
  State<TelaNotificacoes> createState() => _TelaNotificacoesState();
}

class _TelaNotificacoesState extends State<TelaNotificacoes> {
  List<Map<String, dynamic>> _items = [];
  bool _loading = true;
  String? _erro;

  @override
  void initState() {
    super.initState();
    _carregar();
  }

  Future<void> _carregar() async {
    setState(() { _loading = true; _erro = null; });
    try {
      final d = await FuncionarioSstService.notificacoes();
      setState(() => _items = List<Map<String, dynamic>>.from(d['notificacoes'] ?? []));
    } catch (e) {
      setState(() => _erro = e.toString().replaceFirst('Exception: ', ''));
    } finally {
      setState(() => _loading = false);
    }
  }

  Future<void> _marcarLida(int id) async {
    await FuncionarioSstService.marcarLida(id);
    setState(() {
      for (var item in _items) {
        if (item['id'] == id) item['lida'] = true;
      }
    });
    widget.onLidas?.call();
  }

  Future<void> _marcarTodasLidas() async {
    final naolidas = _items.where((i) => i['lida'] == false).toList();
    for (final item in naolidas) {
      await FuncionarioSstService.marcarLida(item['id'] as int);
    }
    setState(() {
      for (var item in _items) item['lida'] = true;
    });
    widget.onLidas?.call();
  }

  IconData _icone(String tipo) {
    switch (tipo) {
      case 'aso': return Icons.medical_information_outlined;
      case 'exame': return Icons.science_outlined;
      case 'treinamento': return Icons.school_outlined;
      default: return Icons.notifications_outlined;
    }
  }

  Color _cor(String tipo) {
    switch (tipo) {
      case 'aso': return Colors.tealAccent;
      case 'exame': return Colors.blueAccent;
      case 'treinamento': return Colors.amberAccent;
      default: return Colors.white60;
    }
  }

  @override
  Widget build(BuildContext context) {
    final naoLidas = _items.where((i) => i['lida'] == false).length;

    return Scaffold(
      appBar: AppBar(
        title: const Text('Notificações'),
        actions: [
          if (naoLidas > 0)
            TextButton(
              onPressed: _marcarTodasLidas,
              child: const Text('Marcar todas como lidas'),
            ),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _erro != null
              ? Center(child: Text(_erro!, style: const TextStyle(color: Colors.redAccent)))
              : _items.isEmpty
                  ? const Center(
                      child: Column(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Icon(Icons.notifications_none, size: 56, color: Colors.white24),
                          SizedBox(height: 12),
                          Text('Nenhuma notificação', style: TextStyle(color: Colors.white54)),
                        ],
                      ),
                    )
                  : RefreshIndicator(
                      onRefresh: _carregar,
                      child: ListView.separated(
                        padding: const EdgeInsets.all(12),
                        itemCount: _items.length,
                        separatorBuilder: (_, __) => const SizedBox(height: 8),
                        itemBuilder: (context, i) {
                          final n = _items[i];
                          final lida = n['lida'] == true;
                          final tipo = n['tipo']?.toString() ?? 'geral';
                          return Card(
                            color: lida
                                ? Theme.of(context).cardColor
                                : Theme.of(context).colorScheme.primaryContainer.withAlpha(60),
                            child: ListTile(
                              leading: CircleAvatar(
                                backgroundColor: _cor(tipo).withAlpha(30),
                                child: Icon(_icone(tipo), color: _cor(tipo), size: 20),
                              ),
                              title: Text(
                                n['titulo']?.toString() ?? '',
                                style: TextStyle(
                                  fontWeight: lida ? FontWeight.normal : FontWeight.bold,
                                  fontSize: 14,
                                ),
                              ),
                              subtitle: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  if ((n['mensagem']?.toString() ?? '').isNotEmpty)
                                    Padding(
                                      padding: const EdgeInsets.only(top: 4),
                                      child: Text(
                                        n['mensagem'].toString(),
                                        style: const TextStyle(fontSize: 12, color: Colors.white70),
                                      ),
                                    ),
                                  Padding(
                                    padding: const EdgeInsets.only(top: 4),
                                    child: Text(
                                      n['criado_em']?.toString() ?? '',
                                      style: const TextStyle(fontSize: 11, color: Colors.white38),
                                    ),
                                  ),
                                ],
                              ),
                              trailing: lida
                                  ? null
                                  : IconButton(
                                      icon: const Icon(Icons.check_circle_outline, size: 20),
                                      tooltip: 'Marcar como lida',
                                      onPressed: () => _marcarLida(n['id'] as int),
                                    ),
                              isThreeLine: true,
                            ),
                          );
                        },
                      ),
                    ),
    );
  }
}
