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
  List<Map<String, dynamic>> _notifs = [];
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
      // Carrega dashboard e notificações em paralelo
      final results = await Future.wait([
        FuncionarioSstService.dashboard(),
        FuncionarioSstService.notificacoes(),
      ]);
      if (!mounted) return;
      final notifData = results[1];
      setState(() {
        _dash = results[0];
        _notifs = List<Map<String, dynamic>>.from(
          (notifData['notificacoes'] as List? ?? []).where((n) => n['lida'] == false),
        );
      });
    } catch (e) {
      if (!mounted) return;
      setState(() => _erro = e.toString().replaceFirst('Exception: ', ''));
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _marcarLida(int id) async {
    try {
      await FuncionarioSstService.marcarLida(id);
      setState(() => _notifs.removeWhere((n) => n['id'] == id));
    } catch (_) {}
  }

  IconData _iconeNotif(String tipo) {
    switch (tipo) {
      case 'aso': return Icons.medical_information_outlined;
      case 'exame': return Icons.science_outlined;
      case 'treinamento': return Icons.school_outlined;
      default: return Icons.notifications_outlined;
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
    final d = _dash ?? {};
    final asoStatus = (d['aso_status'] ?? 'sem_aso').toString();
    final asoValidade = (d['aso_validade'] ?? '-').toString();
    final treinamentosVencidos = (d['treinamentos_vencidos'] ?? 0).toString();
    final solicitacoesAtivas = (d['solicitacoes_ativas'] ?? 0).toString();
    final proximoExame = (d['proximo_agendamento_exame'] ?? 'Sem agenda').toString();

    return RefreshIndicator(
      onRefresh: _carregar,
      child: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          // ── Header ──
          Text(widget.nome, style: Theme.of(context).textTheme.titleLarge),
          Text('${widget.cargo} • ${widget.empresaNome}',
            style: const TextStyle(color: Colors.white60)),
          const SizedBox(height: 16),

          // ── Notificações pendentes (mostradas no topo!) ──
          if (_notifs.isNotEmpty) ...[
            Row(children: [
              const Icon(Icons.notifications_active, color: Colors.amberAccent, size: 18),
              const SizedBox(width: 6),
              Text('${_notifs.length} aviso(s) não lido(s)',
                style: const TextStyle(fontWeight: FontWeight.bold,
                  color: Colors.amberAccent, fontSize: 13)),
            ]),
            const SizedBox(height: 8),
            ..._notifs.take(5).map((n) {
              final tipo = n['tipo']?.toString() ?? 'geral';
              return Card(
                color: Theme.of(context).colorScheme.primaryContainer.withAlpha(80),
                margin: const EdgeInsets.only(bottom: 8),
                child: ListTile(
                  leading: CircleAvatar(
                    backgroundColor: Colors.amberAccent.withAlpha(40),
                    child: Icon(_iconeNotif(tipo),
                      color: Colors.amberAccent, size: 20),
                  ),
                  title: Text(n['titulo']?.toString() ?? '',
                    style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 13)),
                  subtitle: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      if ((n['mensagem']?.toString() ?? '').isNotEmpty)
                        Text(n['mensagem'].toString(),
                          style: const TextStyle(fontSize: 12, color: Colors.white70)),
                      Text(n['criado_em']?.toString() ?? '',
                        style: const TextStyle(fontSize: 11, color: Colors.white38)),
                    ],
                  ),
                  trailing: IconButton(
                    icon: const Icon(Icons.check_circle_outline,
                      size: 20, color: Colors.amberAccent),
                    tooltip: 'Marcar como lido',
                    onPressed: () => _marcarLida(n['id'] as int),
                  ),
                  isThreeLine: true,
                ),
              );
            }),
            const SizedBox(height: 12),
            const Divider(),
            const SizedBox(height: 4),
          ],

          // ── KPI Grid ──
          GridView.count(
            crossAxisCount: 2,
            shrinkWrap: true,
            physics: const NeverScrollableScrollPhysics(),
            crossAxisSpacing: 12,
            mainAxisSpacing: 12,
            childAspectRatio: 1.45,
            children: [
              _ResumoCard(
                titulo: 'ASO',
                valor: asoStatus.toUpperCase(),
                detalhe: 'Validade: $asoValidade',
                icon: Icons.assignment_turned_in_outlined,
                destaque: asoStatus == 'vencido' || asoStatus == 'sem_aso',
              ),
              _ResumoCard(
                titulo: 'Treinamentos',
                valor: treinamentosVencidos,
                detalhe: 'vencido(s)',
                icon: Icons.school_outlined,
                destaque: int.tryParse(treinamentosVencidos) != null &&
                  int.parse(treinamentosVencidos) > 0,
              ),
              _ResumoCard(
                titulo: 'Solicitações',
                valor: solicitacoesAtivas,
                detalhe: 'ativa(s)',
                icon: Icons.medical_services_outlined,
              ),
              _ResumoCard(
                titulo: 'Próximo exame',
                valor: proximoExame == 'Sem agenda' ? '—' : 'Agendado',
                detalhe: proximoExame,
                icon: Icons.event_available_outlined,
              ),
            ],
          ),
          const SizedBox(height: 16),

          // ── Resumo ──
          Card(
            child: Padding(
              padding: const EdgeInsets.all(14),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text('Resumo operacional',
                    style: TextStyle(fontWeight: FontWeight.bold)),
                  const SizedBox(height: 8),
                  Text('Empresa: ${d['empresa_nome'] ?? widget.empresaNome}'),
                  Text('Resultado do último ASO: ${d['aso_resultado'] ?? '-'}'),
                  Text('Treinamentos válidos: ${d['treinamentos_ok'] ?? 0}'),
                ],
              ),
            ),
          ),
          const SizedBox(height: 24),
          Center(
            child: TextButton.icon(
              onPressed: _carregar,
              icon: const Icon(Icons.refresh, size: 16),
              label: const Text('Atualizar dados', style: TextStyle(fontSize: 12)),
            ),
          ),
        ],
      ),
    );
  }
}

class _ResumoCard extends StatelessWidget {
  const _ResumoCard({
    required this.titulo,
    required this.valor,
    required this.detalhe,
    required this.icon,
    this.destaque = false,
  });

  final String titulo;
  final String valor;
  final String detalhe;
  final IconData icon;
  final bool destaque;

  @override
  Widget build(BuildContext context) {
    return Card(
      color: destaque
        ? Theme.of(context).colorScheme.error.withAlpha(30)
        : null,
      child: Padding(
        padding: const EdgeInsets.all(10),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(icon, size: 22,
              color: destaque ? Colors.redAccent : null),
            const SizedBox(height: 8),
            Text(titulo,
              style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600)),
            const SizedBox(height: 3),
            Text(valor,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                fontSize: 16,
                fontWeight: FontWeight.bold,
                color: destaque ? Colors.redAccent : null,
              )),
            const SizedBox(height: 3),
            Text(detalhe,
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                fontSize: 11,
                color: Theme.of(context).textTheme.bodySmall?.color,
              )),
          ],
        ),
      ),
    );
  }
}
