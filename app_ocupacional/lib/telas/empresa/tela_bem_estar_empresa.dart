import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;

import '../../config.dart';
import '../../servicos/empresa_auth_service.dart';

class TelaBemEstarEmpresa extends StatefulWidget {
  const TelaBemEstarEmpresa({super.key});

  @override
  State<TelaBemEstarEmpresa> createState() => _TelaBemEstarEmpresaState();
}

class _TelaBemEstarEmpresaState extends State<TelaBemEstarEmpresa> {
  Map<String, dynamic>? _dados;
  bool _loading = true;
  String? _erro;
  int _dias = 7;

  @override
  void initState() {
    super.initState();
    _carregar();
  }

  Future<void> _carregar() async {
    setState(() { _loading = true; _erro = null; });
    try {
      final token = await EmpresaAuthService.token();
      final r = await http.get(
        Uri.parse('${Config.baseUrl}/api/sst/bem-estar/resumo?dias=$_dias'),
        headers: {'Authorization': 'Bearer $token'},
      );
      if (r.statusCode == 200) {
        setState(() => _dados = jsonDecode(r.body) as Map<String, dynamic>);
      } else {
        throw Exception('Erro ${r.statusCode}');
      }
    } catch (e) {
      setState(() => _erro = e.toString().replaceFirst('Exception: ', ''));
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _marcarResolvido(int id) async {
    final token = await EmpresaAuthService.token();
    await http.patch(
      Uri.parse('${Config.baseUrl}/api/sst/bem-estar/$id/resolvido'),
      headers: {'Authorization': 'Bearer $token'},
    );
    await _carregar();
  }

  void _mudarPeriodo(int dias) {
    setState(() => _dias = dias);
    _carregar();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Bem-estar da Equipe'),
        actions: [
          IconButton(icon: const Icon(Icons.refresh), onPressed: _carregar),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _erro != null
              ? _Erro(mensagem: _erro!, onRetry: _carregar)
              : _buildConteudo(),
    );
  }

  Widget _buildConteudo() {
    final d = _dados ?? {};
    final total = d['total'] as int? ?? 0;
    final medias = d['medias'] as Map<String, dynamic>? ?? {};
    final humor = d['humor_distribuicao'] as List? ?? [];
    final alertas = d['alertas'] as List? ?? [];
    final pedidos = d['pedidos_contato'] as List? ?? [];

    return RefreshIndicator(
      onRefresh: _carregar,
      child: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          // ── filtro período ────────────────────────────────────────────
          Row(
            children: [7, 30, 90].map((d) {
              final ativo = _dias == d;
              return Padding(
                padding: const EdgeInsets.only(right: 8),
                child: ChoiceChip(
                  label: Text('$d dias'),
                  selected: ativo,
                  onSelected: (_) => _mudarPeriodo(d),
                  selectedColor: const Color(0xFF27D3BE).withValues(alpha: 0.2),
                  labelStyle: TextStyle(
                    color: ativo ? const Color(0xFF27D3BE) : Colors.white54,
                    fontWeight: ativo ? FontWeight.w800 : FontWeight.normal,
                  ),
                ),
              );
            }).toList(),
          ),
          const SizedBox(height: 16),

          if (total == 0)
            _vazioCard('Nenhum check-in nos últimos $_dias dias.\nOs funcionários ainda não enviaram dados de bem-estar.')
          else ...[
            // ── KPIs ─────────────────────────────────────────────────
            _secao('📊 Resumo ($total check-ins)'),
            GridView.count(
              crossAxisCount: 2,
              mainAxisSpacing: 10,
              crossAxisSpacing: 10,
              childAspectRatio: 1.4,
              shrinkWrap: true,
              physics: const NeverScrollableScrollPhysics(),
              children: [
                _KpiCard('Saúde Física 💪', medias['saude_fisica'], false),
                _KpiCard('Saúde Mental 🧠', medias['saude_mental'], false),
                _KpiCard('Estresse 😤', medias['nivel_estresse'], true),
                _KpiCard('Satisfação 🏢', medias['satisfacao_trabalho'], false),
              ],
            ),
            const SizedBox(height: 20),

            // ── alertas ───────────────────────────────────────────────
            if (alertas.isNotEmpty) ...[
              _secao('⚠️ Alertas'),
              ...alertas.map((a) => _AlertaCard(a as Map<String, dynamic>)),
              const SizedBox(height: 8),
            ],

            // ── humor ─────────────────────────────────────────────────
            _secao('😊 Humor da Equipe'),
            Card(
              child: Padding(
                padding: const EdgeInsets.all(16),
                child: humor.isEmpty
                    ? _vazioInline('Sem dados')
                    : Column(
                        children: humor.map<Widget>((h) {
                          final item = h as Map<String, dynamic>;
                          final pct = total > 0 ? (item['qtd'] as int) / total : 0.0;
                          return _HumorRow(
                            emoji: _humorEmoji(item['humor'] as String),
                            label: item['label'] as String,
                            qtd: item['qtd'] as int,
                            pct: pct,
                            cor: _humorCor(item['humor'] as String),
                          );
                        }).toList(),
                      ),
              ),
            ),
            const SizedBox(height: 20),

            // ── pedidos contato ───────────────────────────────────────
            _secao('🆘 Pedidos de Contato (${pedidos.length})'),
            if (pedidos.isEmpty)
              _vazioCard('Nenhum pedido pendente 🎉\nNenhum funcionário solicitou contato.')
            else
              ...pedidos.map((p) {
                final item = p as Map<String, dynamic>;
                return _PedidoCard(
                  item: item,
                  onResolvido: () => _marcarResolvido(item['id'] as int),
                );
              }),
          ],

          const SizedBox(height: 24),
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: Colors.white.withValues(alpha: 0.03),
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: Colors.white10),
            ),
            child: const Row(
              children: [
                Icon(Icons.lock_outline, size: 14, color: Colors.white38),
                SizedBox(width: 8),
                Expanded(
                  child: Text(
                    'Dados anônimos. O nome só aparece quando o funcionário solicita contato voluntariamente.',
                    style: TextStyle(fontSize: 11, color: Colors.white38),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _secao(String titulo) => Padding(
        padding: const EdgeInsets.only(bottom: 10),
        child: Text(titulo,
            style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 14, color: Colors.white70)),
      );

  Widget _vazioCard(String msg) => Card(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Text(msg, textAlign: TextAlign.center,
              style: const TextStyle(color: Colors.white54, fontSize: 13)),
        ),
      );

  Widget _vazioInline(String msg) =>
      Text(msg, style: const TextStyle(color: Colors.white54, fontSize: 13));

  String _humorEmoji(String h) =>
      {'otimo': '😄', 'bom': '🙂', 'regular': '😐', 'ruim': '😔', 'pessimo': '😞'}[h] ?? '😐';

  Color _humorCor(String h) => {
        'otimo': const Color(0xFF27D3BE),
        'bom': const Color(0xFF7BAEFF),
        'regular': const Color(0xFFFFD166),
        'ruim': Colors.orange,
        'pessimo': Colors.redAccent,
      }[h] ?? Colors.white38;
}

// ── widgets auxiliares ──────────────────────────────────────────────────────

class _KpiCard extends StatelessWidget {
  const _KpiCard(this.label, this.valor, this.inverso);
  final String label;
  final dynamic valor;
  final bool inverso;

  @override
  Widget build(BuildContext context) {
    final v = (valor as num?)?.toDouble() ?? 0;
    Color cor;
    if (inverso) {
      cor = v >= 4 ? Colors.redAccent : v >= 3 ? Colors.orange : const Color(0xFF27D3BE);
    } else {
      cor = v >= 4 ? const Color(0xFF27D3BE) : v >= 3 ? Colors.orange : Colors.redAccent;
    }
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Text(label, style: const TextStyle(fontSize: 12, color: Colors.white60)),
            Text(v.toStringAsFixed(1),
                style: TextStyle(fontSize: 28, fontWeight: FontWeight.w900, color: cor)),
            Text('média /5', style: const TextStyle(fontSize: 10, color: Colors.white38)),
          ],
        ),
      ),
    );
  }
}

class _HumorRow extends StatelessWidget {
  const _HumorRow({required this.emoji, required this.label, required this.qtd, required this.pct, required this.cor});
  final String emoji, label;
  final int qtd;
  final double pct;
  final Color cor;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Row(
        children: [
          Text(emoji, style: const TextStyle(fontSize: 20)),
          const SizedBox(width: 8),
          SizedBox(width: 64, child: Text(label, style: const TextStyle(fontSize: 12, color: Colors.white60))),
          Expanded(
            child: ClipRRect(
              borderRadius: BorderRadius.circular(99),
              child: LinearProgressIndicator(
                value: pct,
                backgroundColor: Colors.white10,
                valueColor: AlwaysStoppedAnimation(cor),
                minHeight: 8,
              ),
            ),
          ),
          const SizedBox(width: 8),
          Text('$qtd', style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 13)),
        ],
      ),
    );
  }
}

class _AlertaCard extends StatelessWidget {
  const _AlertaCard(this.alerta);
  final Map<String, dynamic> alerta;

  @override
  Widget build(BuildContext context) {
    final critico = (alerta['tipo'] as String).contains('critico');
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: (critico ? Colors.redAccent : Colors.orange).withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: (critico ? Colors.redAccent : Colors.orange).withValues(alpha: 0.25)),
      ),
      child: Row(
        children: [
          Text(critico ? '🔴' : '⚠️', style: const TextStyle(fontSize: 18)),
          const SizedBox(width: 10),
          Expanded(child: Text(alerta['mensagem'] as String,
              style: const TextStyle(fontSize: 13))),
        ],
      ),
    );
  }
}

class _PedidoCard extends StatelessWidget {
  const _PedidoCard({required this.item, required this.onResolvido});
  final Map<String, dynamic> item;
  final VoidCallback onResolvido;

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: const EdgeInsets.only(bottom: 10),
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Icon(Icons.person_outline, size: 18, color: Color(0xFF27D3BE)),
                const SizedBox(width: 6),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(item['nome'] as String,
                          style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 14)),
                      Text(item['cargo'] as String,
                          style: const TextStyle(fontSize: 12, color: Colors.white54)),
                    ],
                  ),
                ),
              ],
            ),
            const SizedBox(height: 8),
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 3),
              decoration: BoxDecoration(
                color: Colors.orange.withValues(alpha: 0.12),
                borderRadius: BorderRadius.circular(99),
              ),
              child: Text(item['tipo_ajuda'] as String,
                  style: const TextStyle(fontSize: 12, color: Colors.orange, fontWeight: FontWeight.w700)),
            ),
            if ((item['mensagem'] as String).isNotEmpty) ...[
              const SizedBox(height: 8),
              Text('"${item['mensagem']}"',
                  style: const TextStyle(fontSize: 12, color: Colors.white54, fontStyle: FontStyle.italic)),
            ],
            const SizedBox(height: 10),
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text(item['data'] as String,
                    style: const TextStyle(fontSize: 11, color: Colors.white38)),
                TextButton.icon(
                  onPressed: onResolvido,
                  icon: const Icon(Icons.check_circle_outline, size: 16),
                  label: const Text('Marcar como atendido'),
                  style: TextButton.styleFrom(foregroundColor: const Color(0xFF00C896)),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}

class _Erro extends StatelessWidget {
  const _Erro({required this.mensagem, required this.onRetry});
  final String mensagem;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.cloud_off_outlined, size: 44, color: Colors.white38),
            const SizedBox(height: 12),
            Text(mensagem, textAlign: TextAlign.center, style: const TextStyle(color: Colors.white54)),
            const SizedBox(height: 12),
            OutlinedButton.icon(onPressed: onRetry,
                icon: const Icon(Icons.refresh), label: const Text('Tentar novamente')),
          ],
        ),
      ),
    );
  }
}
