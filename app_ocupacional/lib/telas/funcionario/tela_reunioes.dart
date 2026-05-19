import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../../servicos/funcionario_sst_service.dart';

class TelaReunioesFunc extends StatefulWidget {
  const TelaReunioesFunc({super.key});

  @override
  State<TelaReunioesFunc> createState() => _TelaReunioesState();
}

class _TelaReunioesState extends State<TelaReunioesFunc> {
  List<dynamic> _lista = const [];
  String? _erro;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _carregar();
  }

  Future<void> _carregar() async {
    setState(() { _loading = true; _erro = null; });
    try {
      final data = await FuncionarioSstService.reunioes();
      if (!mounted) return;
      setState(() => _lista = (data['reunioes'] as List<dynamic>? ?? []));
    } catch (e) {
      if (!mounted) return;
      setState(() => _erro = e.toString().replaceFirst('Exception: ', ''));
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _entrar(String link) async {
    final uri = Uri.tryParse(link);
    if (uri == null) return;
    if (await canLaunchUrl(uri)) {
      await launchUrl(uri, mode: LaunchMode.externalApplication);
    } else {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Não foi possível abrir o link da reunião.')),
      );
    }
  }

  Color _statusColor(String status) {
    switch (status) {
      case 'em_andamento': return Colors.tealAccent;
      case 'agendada':     return Colors.blueAccent;
      case 'encerrada':    return Colors.white38;
      default:             return Colors.white38;
    }
  }

  IconData _statusIcon(String status) {
    switch (status) {
      case 'em_andamento': return Icons.fiber_manual_record;
      case 'agendada':     return Icons.schedule;
      case 'encerrada':    return Icons.check_circle_outline;
      default:             return Icons.info_outline;
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) return const Center(child: CircularProgressIndicator());

    if (_erro != null) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.wifi_off_outlined, size: 48, color: Colors.redAccent),
              const SizedBox(height: 12),
              Text(_erro!, textAlign: TextAlign.center,
                style: const TextStyle(color: Colors.redAccent)),
              const SizedBox(height: 16),
              FilledButton.icon(
                onPressed: _carregar,
                icon: const Icon(Icons.refresh),
                label: const Text('Tentar novamente'),
              ),
            ],
          ),
        ),
      );
    }

    if (_lista.isEmpty) {
      return RefreshIndicator(
        onRefresh: _carregar,
        child: ListView(
          padding: const EdgeInsets.all(24),
          children: const [
            SizedBox(height: 80),
            Icon(Icons.videocam_off_outlined, size: 64, color: Colors.white24),
            SizedBox(height: 16),
            Text(
              'Nenhuma reunião agendada',
              textAlign: TextAlign.center,
              style: TextStyle(fontSize: 16, color: Colors.white54),
            ),
            SizedBox(height: 8),
            Text(
              'Quando a empresa agendar uma reunião para você, ela aparecerá aqui.',
              textAlign: TextAlign.center,
              style: TextStyle(fontSize: 13, color: Colors.white38),
            ),
          ],
        ),
      );
    }

    return RefreshIndicator(
      onRefresh: _carregar,
      child: ListView.separated(
        padding: const EdgeInsets.all(14),
        itemCount: _lista.length,
        separatorBuilder: (_, __) => const SizedBox(height: 10),
        itemBuilder: (context, i) {
          final r = _lista[i] as Map<String, dynamic>;
          final status = r['status']?.toString() ?? '';
          final statusLabel = r['status_label']?.toString() ?? '';
          final link = r['link']?.toString() ?? '';
          final emAndamento = status == 'em_andamento';
          final agendada = status == 'agendada';

          return Card(
            elevation: emAndamento ? 4 : 0,
            shape: RoundedRectangleBorder(
              borderRadius: BorderRadius.circular(16),
              side: emAndamento
                  ? const BorderSide(color: Colors.tealAccent, width: 1.5)
                  : BorderSide.none,
            ),
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  // Status badge
                  Row(
                    children: [
                      Icon(_statusIcon(status), size: 13, color: _statusColor(status)),
                      const SizedBox(width: 5),
                      Text(statusLabel,
                        style: TextStyle(
                          fontSize: 11,
                          fontWeight: FontWeight.w700,
                          color: _statusColor(status),
                          letterSpacing: .04,
                        )),
                      if (emAndamento) ...[
                        const SizedBox(width: 6),
                        Container(
                          padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                          decoration: BoxDecoration(
                            color: Colors.tealAccent.withAlpha(30),
                            borderRadius: BorderRadius.circular(99),
                          ),
                          child: const Text('AO VIVO',
                            style: TextStyle(fontSize: 9, fontWeight: FontWeight.w800,
                              color: Colors.tealAccent, letterSpacing: .08)),
                        ),
                      ],
                    ],
                  ),
                  const SizedBox(height: 8),

                  // Título
                  Text(r['titulo']?.toString() ?? '',
                    style: TextStyle(
                      fontSize: 15,
                      fontWeight: FontWeight.bold,
                      color: emAndamento ? Colors.tealAccent : null,
                    )),
                  const SizedBox(height: 6),

                  // Data e hora
                  Row(
                    children: [
                      const Icon(Icons.schedule, size: 14, color: Colors.white38),
                      const SizedBox(width: 4),
                      Text(r['data_hora_fmt']?.toString() ?? '',
                        style: const TextStyle(fontSize: 13, color: Colors.white60)),
                      const SizedBox(width: 10),
                      const Icon(Icons.timer_outlined, size: 14, color: Colors.white38),
                      const SizedBox(width: 4),
                      Text('${r['duracao_minutos'] ?? 60} min',
                        style: const TextStyle(fontSize: 13, color: Colors.white60)),
                    ],
                  ),

                  // Descrição
                  if ((r['descricao']?.toString() ?? '').isNotEmpty) ...[
                    const SizedBox(height: 8),
                    Text(r['descricao'].toString(),
                      style: const TextStyle(fontSize: 12, color: Colors.white54),
                      maxLines: 2,
                      overflow: TextOverflow.ellipsis),
                  ],

                  // Botão entrar
                  if ((agendada || emAndamento) && link.isNotEmpty) ...[
                    const SizedBox(height: 12),
                    SizedBox(
                      width: double.infinity,
                      child: FilledButton.icon(
                        onPressed: () => _entrar(link),
                        icon: const Icon(Icons.videocam_outlined, size: 18),
                        label: Text(emAndamento
                          ? 'Entrar agora'
                          : 'Acessar link da reunião'),
                        style: FilledButton.styleFrom(
                          backgroundColor: emAndamento
                              ? Colors.tealAccent
                              : Theme.of(context).colorScheme.primary,
                          foregroundColor: emAndamento ? Colors.black : null,
                        ),
                      ),
                    ),
                  ],
                ],
              ),
            ),
          );
        },
      ),
    );
  }
}
