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
      if (mounted) setState(() => _loading = false);
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
      for (final item in _items) item['lida'] = true;
    });
    widget.onLidas?.call();
  }

  Future<void> _deletar(int id) async {
    await FuncionarioSstService.deletarNotificacao(id);
    setState(() => _items.removeWhere((i) => i['id'] == id));
  }

  Future<void> _limparLidas() async {
    final temLidas = _items.any((i) => i['lida'] == true);
    if (!temLidas) return;

    final confirmar = await showDialog<bool>(
      context: context,
      builder: (_) => AlertDialog(
        backgroundColor: const Color(0xFF0D1C29),
        title: const Text('Limpar notificações lidas'),
        content: const Text('Remover todas as notificações já lidas?'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(context, false), child: const Text('Cancelar')),
          TextButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('Limpar', style: TextStyle(color: Colors.redAccent)),
          ),
        ],
      ),
    );
    if (confirmar != true) return;

    await FuncionarioSstService.limparNotificacoesLidas();
    setState(() => _items.removeWhere((i) => i['lida'] == true));
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
    final temLidas = _items.any((i) => i['lida'] == true);

    return Scaffold(
      appBar: AppBar(
        title: const Text('Notificações'),
        actions: [
          if (naoLidas > 0)
            TextButton(
              onPressed: _marcarTodasLidas,
              child: const Text('Marcar todas lidas'),
            ),
          if (temLidas)
            IconButton(
              icon: const Icon(Icons.delete_sweep_outlined),
              tooltip: 'Limpar lidas',
              onPressed: _limparLidas,
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
                  : Column(
                      children: [
                        if (temLidas)
                          Padding(
                            padding: const EdgeInsets.fromLTRB(16, 10, 16, 0),
                            child: Row(
                              children: [
                                const Icon(Icons.swipe_left, size: 14, color: Colors.white38),
                                const SizedBox(width: 6),
                                Text(
                                  'Deslize para a esquerda para apagar mensagens lidas',
                                  style: Theme.of(context).textTheme.bodySmall?.copyWith(color: Colors.white38),
                                ),
                              ],
                            ),
                          ),
                        Expanded(
                          child: RefreshIndicator(
                            onRefresh: _carregar,
                            child: ListView.separated(
                              padding: const EdgeInsets.all(12),
                              itemCount: _items.length,
                              separatorBuilder: (_, __) => const SizedBox(height: 8),
                              itemBuilder: (context, i) {
                                final n = _items[i];
                                final lida = n['lida'] == true;
                                final tipo = n['tipo']?.toString() ?? 'geral';
                                final id = n['id'] as int;

                                final card = Card(
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
                                            onPressed: () => _marcarLida(id),
                                          ),
                                    isThreeLine: true,
                                  ),
                                );

                                // Swipe-to-delete apenas em notificações lidas
                                if (!lida) return card;

                                return Dismissible(
                                  key: ValueKey(id),
                                  direction: DismissDirection.endToStart,
                                  background: Container(
                                    alignment: Alignment.centerRight,
                                    padding: const EdgeInsets.only(right: 20),
                                    decoration: BoxDecoration(
                                      color: Colors.redAccent.withOpacity(0.15),
                                      borderRadius: BorderRadius.circular(12),
                                    ),
                                    child: const Column(
                                      mainAxisSize: MainAxisSize.min,
                                      children: [
                                        Icon(Icons.delete_outline, color: Colors.redAccent),
                                        SizedBox(height: 4),
                                        Text('Apagar', style: TextStyle(color: Colors.redAccent, fontSize: 11)),
                                      ],
                                    ),
                                  ),
                                  confirmDismiss: (_) async {
                                    await _deletar(id);
                                    return true;
                                  },
                                  child: card,
                                );
                              },
                            ),
                          ),
                        ),
                      ],
                    ),
    );
  }
}
