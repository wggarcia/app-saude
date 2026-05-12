import 'package:flutter/material.dart';
import '../../servicos/funcionario_sst_service.dart';

class TelaMeusTreinamentos extends StatefulWidget {
  const TelaMeusTreinamentos({super.key});

  @override
  State<TelaMeusTreinamentos> createState() => _TelaMeusTreinamentosState();
}

class _TelaMeusTreinamentosState extends State<TelaMeusTreinamentos> {
  static const _bg = Color(0xFF04131F);
  static const _accent = Color(0xFF39D0C3);

  List<dynamic> _treinamentos = [];
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
      final data = await FuncionarioSSTService.getMeusTreinamentos();
      if (!mounted) return;
      setState(() {
        _treinamentos = data['treinamentos'] as List<dynamic>? ?? [];
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

  @override
  Widget build(BuildContext context) {
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
                        child: CircularProgressIndicator(color: _accent),
                      ),
                    ),
                  if (_erro != null && !_loading)
                    _ErroCard(mensagem: _erro!, onRetry: _carregar),
                  if (!_loading && _erro == null && _treinamentos.isEmpty)
                    const _VazioCard(mensagem: 'Nenhum treinamento encontrado.'),
                  if (!_loading && _erro == null)
                    ..._treinamentos.map((item) {
                      final t = item as Map<String, dynamic>;
                      return Padding(
                        padding: const EdgeInsets.only(bottom: 12),
                        child: _TreinamentoCard(treinamento: t),
                      );
                    }),
                ]),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _TreinamentoCard extends StatelessWidget {
  const _TreinamentoCard({required this.treinamento});

  final Map<String, dynamic> treinamento;

  @override
  Widget build(BuildContext context) {
    final vencido = treinamento['vencido'] == true;
    final badgeColor =
        vencido ? const Color(0xFFFF6B6B) : const Color(0xFF1DD1A1);
    final badgeText = vencido ? 'VENCIDO' : 'EM DIA';

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0xFF0B2333),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: badgeColor.withValues(alpha: 0.25),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    if (treinamento['nr'] != null)
                      Text(
                        'NR ${treinamento['nr']}',
                        style: const TextStyle(
                          color: Color(0xFF39D0C3),
                          fontSize: 12,
                          fontWeight: FontWeight.w700,
                        ),
                      ),
                    const SizedBox(height: 2),
                    Text(
                      treinamento['titulo']?.toString() ?? 'Treinamento',
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 15,
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(width: 8),
              Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                decoration: BoxDecoration(
                  color: badgeColor.withValues(alpha: 0.15),
                  borderRadius: BorderRadius.circular(20),
                  border: Border.all(color: badgeColor.withValues(alpha: 0.5)),
                ),
                child: Text(
                  badgeText,
                  style: TextStyle(
                    color: badgeColor,
                    fontSize: 11,
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 10),
          if (treinamento['carga_horaria'] != null)
            _InfoRow(
              label: 'Carga horaria',
              valor: '${treinamento['carga_horaria']}h',
            ),
          if (treinamento['data_realizacao'] != null)
            _InfoRow(
              label: 'Realizado em',
              valor: treinamento['data_realizacao'].toString(),
            ),
          if (treinamento['data_vencimento'] != null)
            _InfoRow(
              label: 'Vencimento',
              valor: treinamento['data_vencimento'].toString(),
            ),
          if (treinamento['instrutor'] != null)
            _InfoRow(
              label: 'Instrutor',
              valor: treinamento['instrutor'].toString(),
            ),
        ],
      ),
    );
  }
}

class _InfoRow extends StatelessWidget {
  const _InfoRow({required this.label, required this.valor});

  final String label;
  final String valor;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 4),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 100,
            child: Text(
              label,
              style: TextStyle(
                color: Colors.white.withValues(alpha: 0.6),
                fontSize: 13,
              ),
            ),
          ),
          Expanded(
            child: Text(
              valor,
              style: const TextStyle(color: Colors.white, fontSize: 13),
            ),
          ),
        ],
      ),
    );
  }
}

class _VazioCard extends StatelessWidget {
  const _VazioCard({required this.mensagem});

  final String mensagem;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(32),
      alignment: Alignment.center,
      child: Text(
        mensagem,
        style: TextStyle(color: Colors.white.withValues(alpha: 0.55)),
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
        border: Border.all(
            color: const Color(0xFFFF6B6B).withValues(alpha: 0.4)),
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
