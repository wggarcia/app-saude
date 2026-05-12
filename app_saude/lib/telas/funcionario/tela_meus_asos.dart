import 'package:flutter/material.dart';
import '../../servicos/funcionario_sst_service.dart';

class TelaMeusAsos extends StatefulWidget {
  const TelaMeusAsos({super.key});

  @override
  State<TelaMeusAsos> createState() => _TelaMeusAsosState();
}

class _TelaMeusAsosState extends State<TelaMeusAsos> {
  static const _bg = Color(0xFF04131F);
  static const _accent = Color(0xFF39D0C3);

  List<dynamic> _asos = [];
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
      final data = await FuncionarioSSTService.getMeusAsos();
      if (!mounted) return;
      final lista = (data['asos'] as List<dynamic>? ?? []);
      lista.sort((a, b) {
        final dA = (a as Map<String, dynamic>)['data_emissao']?.toString() ?? '';
        final dB = (b as Map<String, dynamic>)['data_emissao']?.toString() ?? '';
        return dB.compareTo(dA);
      });
      setState(() {
        _asos = lista;
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
                  if (!_loading && _erro == null && _asos.isEmpty)
                    const _VazioCard(mensagem: 'Nenhum ASO encontrado.'),
                  if (!_loading && _erro == null)
                    ..._asos.map((item) {
                      final aso = item as Map<String, dynamic>;
                      return Padding(
                        padding: const EdgeInsets.only(bottom: 12),
                        child: _AsoCard(aso: aso),
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

class _AsoCard extends StatelessWidget {
  const _AsoCard({required this.aso});

  final Map<String, dynamic> aso;

  @override
  Widget build(BuildContext context) {
    final vencido = aso['vencido'] == true;
    final diasVencer = aso['dias_vencer'];
    final alerta = !vencido && diasVencer != null && (diasVencer as num).toInt() <= 30;

    Color badgeColor;
    String badgeText;
    if (vencido) {
      badgeColor = const Color(0xFFFF6B6B);
      badgeText = 'VENCIDO';
    } else if (alerta) {
      badgeColor = const Color(0xFFFFA657);
      badgeText = 'VENCE EM ${(diasVencer as num).toInt()} DIAS';
    } else {
      badgeColor = const Color(0xFF1DD1A1);
      badgeText = 'VALIDO';
    }

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
            children: [
              Expanded(
                child: Text(
                  aso['tipo_display']?.toString() ?? 'ASO',
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 16,
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ),
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
          _InfoRow(
            label: 'Resultado',
            valor: aso['resultado_display']?.toString() ?? '-',
          ),
          _InfoRow(
            label: 'Emissao',
            valor: aso['data_emissao']?.toString() ?? '-',
          ),
          _InfoRow(
            label: 'Validade',
            valor: aso['data_validade']?.toString() ?? '-',
          ),
          _InfoRow(
            label: 'Medico',
            valor: aso['medico_responsavel']?.toString() ?? '-',
          ),
          if (aso['crm'] != null)
            _InfoRow(label: 'CRM', valor: aso['crm'].toString()),
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
            width: 80,
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
