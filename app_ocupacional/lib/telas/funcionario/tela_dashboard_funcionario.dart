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
          Text(widget.nome, style: Theme.of(context).textTheme.titleLarge),
          Text('${widget.cargo} • ${widget.empresaNome}'),
          const SizedBox(height: 16),
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
              ),
              _ResumoCard(
                titulo: 'Treinamentos',
                valor: treinamentosVencidos,
                detalhe: 'vencido(s)',
                icon: Icons.school_outlined,
              ),
              _ResumoCard(
                titulo: 'Solicitações',
                valor: solicitacoesAtivas,
                detalhe: 'ativa(s)',
                icon: Icons.medical_services_outlined,
              ),
              _ResumoCard(
                titulo: 'Próximo exame',
                valor: proximoExame == 'Sem agenda' ? 'Sem agenda' : 'Agendado',
                detalhe: proximoExame,
                icon: Icons.event_available_outlined,
              ),
            ],
          ),
          const SizedBox(height: 16),
          Card(
            child: Padding(
              padding: const EdgeInsets.all(14),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    'Resumo operacional',
                    style: TextStyle(fontWeight: FontWeight.bold),
                  ),
                  const SizedBox(height: 8),
                  Text('Empresa: ${d['empresa_nome'] ?? widget.empresaNome}'),
                  Text('Resultado do último ASO: ${d['aso_resultado'] ?? '-'}'),
                  Text('Treinamentos válidos: ${d['treinamentos_ok'] ?? 0}'),
                ],
              ),
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
  });

  final String titulo;
  final String valor;
  final String detalhe;
  final IconData icon;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(icon, size: 22),
            const SizedBox(height: 14),
            Text(
              titulo,
              style: const TextStyle(
                fontSize: 12,
                fontWeight: FontWeight.w600,
              ),
            ),
            const SizedBox(height: 6),
            Text(
              valor,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
              style: const TextStyle(
                fontSize: 16,
                fontWeight: FontWeight.bold,
              ),
            ),
            const SizedBox(height: 4),
            Text(
              detalhe,
              maxLines: 2,
              overflow: TextOverflow.ellipsis,
              style: TextStyle(
                color: Theme.of(context).textTheme.bodySmall?.color,
              ),
            ),
          ],
        ),
      ),
    );
  }
}
