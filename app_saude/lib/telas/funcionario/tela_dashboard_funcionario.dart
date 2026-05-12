import 'package:flutter/material.dart';
import '../../servicos/funcionario_sst_service.dart';

class TelaDashboardFuncionario extends StatefulWidget {
  const TelaDashboardFuncionario({
    super.key,
    required this.nomeInicial,
    required this.cargoInicial,
    required this.empresaNomeInicial,
  });

  final String nomeInicial;
  final String cargoInicial;
  final String empresaNomeInicial;

  @override
  State<TelaDashboardFuncionario> createState() =>
      _TelaDashboardFuncionarioState();
}

class _TelaDashboardFuncionarioState extends State<TelaDashboardFuncionario> {
  static const _bg = Color(0xFF04131F);
  static const _card = Color(0xFF0B2333);
  static const _accent = Color(0xFF39D0C3);

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
      final data = await FuncionarioSSTService.getDashboard();
      if (!mounted) return;
      setState(() {
        _dados = data;
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _erro = e.toString().replaceFirst('Exception: ', '');
        _loading = false;
      });
    }
  }

  Color _corAso(String status) {
    return switch (status) {
      'ok' => const Color(0xFF1DD1A1),
      'alerta' => const Color(0xFFFFA657),
      _ => const Color(0xFFFF6B6B),
    };
  }

  @override
  Widget build(BuildContext context) {
    final nome = _dados?['nome']?.toString() ?? widget.nomeInicial;
    final cargo = _dados?['cargo']?.toString() ?? widget.cargoInicial;
    final empresa = _dados?['empresa_nome']?.toString() ?? widget.empresaNomeInicial;
    final asoStatus = _dados?['aso_status']?.toString() ?? 'sem_aso';
    final asoValidade = _dados?['aso_validade']?.toString();
    final asoDiasVencer = _dados?['aso_dias_vencer'];
    final treinamentosTotal = _dados?['treinamentos_total'] ?? 0;
    final treinamentosVencidos = _dados?['treinamentos_vencidos'] ?? 0;
    final treinamentosOk = _dados?['treinamentos_ok'] ?? 0;

    return Scaffold(
      backgroundColor: _bg,
      body: RefreshIndicator(
        color: _accent,
        onRefresh: _carregar,
        child: CustomScrollView(
          slivers: [
            SliverPadding(
              padding: const EdgeInsets.fromLTRB(16, 16, 16, 28),
              sliver: SliverList(
                delegate: SliverChildListDelegate([
                  if (_loading)
                    const Center(
                      child: Padding(
                        padding: EdgeInsets.symmetric(vertical: 60),
                        child: CircularProgressIndicator(
                            color: Color(0xFF39D0C3)),
                      ),
                    ),
                  if (_erro != null && !_loading)
                    _ErroCard(mensagem: _erro!, onRetry: _carregar),
                  if (!_loading && _erro == null) ...[
                    _BoasVindasCard(
                      nome: nome,
                      cargo: cargo,
                      empresa: empresa,
                    ),
                    const SizedBox(height: 16),
                    _AsoStatusCard(
                      status: asoStatus,
                      validade: asoValidade,
                      diasVencer: asoDiasVencer,
                      cor: _corAso(asoStatus),
                    ),
                    const SizedBox(height: 16),
                    _TreinamentosCard(
                      total: treinamentosTotal,
                      vencidos: treinamentosVencidos,
                      ok: treinamentosOk,
                    ),
                  ],
                ]),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _BoasVindasCard extends StatelessWidget {
  const _BoasVindasCard({
    required this.nome,
    required this.cargo,
    required this.empresa,
  });

  final String nome;
  final String cargo;
  final String empresa;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        gradient: const LinearGradient(
          colors: [Color(0xFF12324B), Color(0xFF0A1B29)],
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
        ),
        borderRadius: BorderRadius.circular(16),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'Ola, $nome',
            style: const TextStyle(
              color: Colors.white,
              fontSize: 22,
              fontWeight: FontWeight.w800,
            ),
          ),
          const SizedBox(height: 6),
          Text(
            cargo,
            style: const TextStyle(
              color: Color(0xFF39D0C3),
              fontSize: 14,
              fontWeight: FontWeight.w600,
            ),
          ),
          const SizedBox(height: 4),
          Text(
            empresa,
            style: TextStyle(
              color: Colors.white.withValues(alpha: 0.6),
              fontSize: 13,
            ),
          ),
        ],
      ),
    );
  }
}

class _AsoStatusCard extends StatelessWidget {
  const _AsoStatusCard({
    required this.status,
    required this.validade,
    required this.diasVencer,
    required this.cor,
  });

  final String status;
  final String? validade;
  final dynamic diasVencer;
  final Color cor;

  String get _titulo {
    return switch (status) {
      'ok' => 'ASO Valido',
      'alerta' => 'ASO Vencendo em breve',
      'vencido' => 'ASO Vencido',
      _ => 'Sem ASO cadastrado',
    };
  }

  String get _descricao {
    if (status == 'sem_aso') return 'Nenhum ASO encontrado no sistema.';
    if (validade != null && diasVencer != null) {
      final dias = (diasVencer as num).toInt();
      if (dias < 0) {
        return 'Validade: $validade • Vencido ha ${dias.abs()} dias';
      }
      return 'Validade: $validade • Vence em $dias dias';
    }
    if (validade != null) return 'Validade: $validade';
    return '';
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0xFF0B2333),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: cor.withValues(alpha: 0.4)),
      ),
      child: Row(
        children: [
          Container(
            padding: const EdgeInsets.all(10),
            decoration: BoxDecoration(
              color: cor.withValues(alpha: 0.15),
              borderRadius: BorderRadius.circular(12),
            ),
            child: Icon(Icons.assignment_turned_in_outlined, color: cor),
          ),
          const SizedBox(width: 14),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  'Exame Ocupacional (ASO)',
                  style: TextStyle(
                    color: Color(0xFF9CC4DB),
                    fontSize: 12,
                  ),
                ),
                const SizedBox(height: 2),
                Text(
                  _titulo,
                  style: TextStyle(
                    color: cor,
                    fontSize: 16,
                    fontWeight: FontWeight.w700,
                  ),
                ),
                if (_descricao.isNotEmpty) ...[
                  const SizedBox(height: 4),
                  Text(
                    _descricao,
                    style: TextStyle(
                      color: Colors.white.withValues(alpha: 0.6),
                      fontSize: 13,
                    ),
                  ),
                ],
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _TreinamentosCard extends StatelessWidget {
  const _TreinamentosCard({
    required this.total,
    required this.vencidos,
    required this.ok,
  });

  final dynamic total;
  final dynamic vencidos;
  final dynamic ok;

  @override
  Widget build(BuildContext context) {
    final vencidosInt = (vencidos as num).toInt();
    final okInt = (ok as num).toInt();
    final totalInt = (total as num).toInt();

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0xFF0B2333),
        borderRadius: BorderRadius.circular(16),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Row(
            children: [
              Icon(Icons.school_outlined, color: Color(0xFF39D0C3), size: 20),
              SizedBox(width: 8),
              Text(
                'Treinamentos',
                style: TextStyle(
                  color: Colors.white,
                  fontSize: 16,
                  fontWeight: FontWeight.w700,
                ),
              ),
            ],
          ),
          const SizedBox(height: 14),
          Row(
            children: [
              _MetricaItem(
                valor: '$totalInt',
                label: 'Total',
                cor: Colors.white,
              ),
              const SizedBox(width: 12),
              _MetricaItem(
                valor: '$okInt',
                label: 'Em dia',
                cor: const Color(0xFF1DD1A1),
              ),
              const SizedBox(width: 12),
              _MetricaItem(
                valor: '$vencidosInt',
                label: 'Vencidos',
                cor: vencidosInt > 0
                    ? const Color(0xFFFF6B6B)
                    : const Color(0xFF9CC4DB),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _MetricaItem extends StatelessWidget {
  const _MetricaItem({
    required this.valor,
    required this.label,
    required this.cor,
  });

  final String valor;
  final String label;
  final Color cor;

  @override
  Widget build(BuildContext context) {
    return Expanded(
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 12),
        decoration: BoxDecoration(
          color: const Color(0xFF112D40),
          borderRadius: BorderRadius.circular(12),
        ),
        child: Column(
          children: [
            Text(
              valor,
              style: TextStyle(
                color: cor,
                fontSize: 22,
                fontWeight: FontWeight.w800,
              ),
            ),
            const SizedBox(height: 2),
            Text(
              label,
              style: TextStyle(
                color: Colors.white.withValues(alpha: 0.6),
                fontSize: 12,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _ErroCard extends StatelessWidget {
  const _ErroCard({required this.mensagem, required this.onRetry});

  final String mensagem;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.symmetric(vertical: 20),
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: const Color(0xFF4A1010),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: const Color(0xFFFF6B6B).withValues(alpha: 0.4)),
      ),
      child: Column(
        children: [
          const Icon(Icons.error_outline, color: Color(0xFFFF6B6B), size: 32),
          const SizedBox(height: 8),
          Text(
            mensagem,
            textAlign: TextAlign.center,
            style: const TextStyle(color: Color(0xFFFF6B6B)),
          ),
          const SizedBox(height: 12),
          FilledButton(
            onPressed: onRetry,
            style: FilledButton.styleFrom(
              backgroundColor: const Color(0xFF39D0C3),
              foregroundColor: const Color(0xFF04131F),
            ),
            child: const Text('Tentar novamente'),
          ),
        ],
      ),
    );
  }
}
