import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;

import '../../config.dart';
import '../../servicos/funcionario_auth_service.dart';

class TelaBemEstar extends StatefulWidget {
  const TelaBemEstar({super.key});

  @override
  State<TelaBemEstar> createState() => _TelaBemEstarState();
}

class _TelaBemEstarState extends State<TelaBemEstar> {
  // ── estado do formulário ─────────────────────────────────────────────────
  String _humor = 'bom';
  int _saudeFisica = 3;
  int _saudeMental = 3;
  int _estresse = 3;
  int _satisfacao = 3;
  final _msgCtrl = TextEditingController();
  bool _precisaAjuda = false;
  String _tipoAjuda = 'saude_mental';
  bool _querContato = false;
  bool _enviando = false;
  bool _enviado = false;

  // ── histórico ───────────────────────────────────────────────────────────
  List<Map<String, dynamic>> _historico = [];
  bool _carregandoHistorico = true;

  @override
  void initState() {
    super.initState();
    _carregarHistorico();
  }

  @override
  void dispose() {
    _msgCtrl.dispose();
    super.dispose();
  }

  Future<void> _carregarHistorico() async {
    setState(() => _carregandoHistorico = true);
    try {
      final token = await FuncionarioAuthService.token();
      final r = await http.get(
        Uri.parse('${Config.baseUrl}/api/funcionario/bem-estar'),
        headers: {'Authorization': 'Bearer $token'},
      );
      if (r.statusCode == 200) {
        final data = jsonDecode(r.body) as Map<String, dynamic>;
        setState(() => _historico = List<Map<String, dynamic>>.from(data['checkins'] ?? []));
      }
    } catch (_) {}
    if (mounted) setState(() => _carregandoHistorico = false);
  }

  Future<void> _enviar() async {
    setState(() => _enviando = true);
    try {
      final token = await FuncionarioAuthService.token();
      final r = await http.post(
        Uri.parse('${Config.baseUrl}/api/funcionario/bem-estar'),
        headers: {
          'Content-Type': 'application/json',
          'Authorization': 'Bearer $token',
        },
        body: jsonEncode({
          'humor': _humor,
          'saude_fisica': _saudeFisica,
          'saude_mental': _saudeMental,
          'nivel_estresse': _estresse,
          'satisfacao_trabalho': _satisfacao,
          'mensagem': _msgCtrl.text.trim(),
          'precisa_ajuda': _precisaAjuda,
          'tipo_ajuda': _precisaAjuda ? _tipoAjuda : '',
          'quer_contato': _precisaAjuda && _querContato,
        }),
      );
      if (r.statusCode == 201) {
        setState(() { _enviado = true; _enviando = false; });
        await _carregarHistorico();
      } else {
        throw Exception('Erro ${r.statusCode}');
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Erro ao enviar: $e'), backgroundColor: Colors.red),
        );
        setState(() => _enviando = false);
      }
    }
  }

  void _novoCheckin() => setState(() {
    _enviado = false;
    _humor = 'bom';
    _saudeFisica = 3;
    _saudeMental = 3;
    _estresse = 3;
    _satisfacao = 3;
    _msgCtrl.clear();
    _precisaAjuda = false;
    _querContato = false;
  });

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Meu Bem-estar')),
      body: _enviado ? _buildSucesso() : _buildFormulario(),
    );
  }

  // ── tela de sucesso ──────────────────────────────────────────────────────
  Widget _buildSucesso() {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.favorite, size: 72, color: Color(0xFF27D3BE)),
            const SizedBox(height: 20),
            Text('Obrigado pelo check-in!',
                style: Theme.of(context).textTheme.headlineSmall?.copyWith(fontWeight: FontWeight.w800),
                textAlign: TextAlign.center),
            const SizedBox(height: 12),
            Text(
              'Suas informações foram registradas de forma anônima.\n'
              'Juntos construímos um ambiente de trabalho mais saudável.',
              textAlign: TextAlign.center,
              style: Theme.of(context).textTheme.bodyMedium?.copyWith(color: Colors.white60),
            ),
            const SizedBox(height: 32),
            ElevatedButton.icon(
              onPressed: _novoCheckin,
              icon: const Icon(Icons.refresh),
              label: const Text('Novo check-in'),
            ),
            const SizedBox(height: 40),
            if (_historico.isNotEmpty) _buildHistorico(),
          ],
        ),
      ),
    );
  }

  // ── formulário principal ─────────────────────────────────────────────────
  Widget _buildFormulario() {
    return ListView(
      padding: const EdgeInsets.all(20),
      children: [
        _secao('Como você está hoje?'),
        _humorSelector(),
        const SizedBox(height: 24),
        _secao('Avalie de 1 a 5'),
        _sliderItem('Saúde física 💪', _saudeFisica, (v) => setState(() => _saudeFisica = v)),
        _sliderItem('Saúde mental 🧠', _saudeMental, (v) => setState(() => _saudeMental = v)),
        _sliderItem('Nível de estresse 😤', _estresse, (v) => setState(() => _estresse = v), inverso: true),
        _sliderItem('Satisfação no trabalho 🏢', _satisfacao, (v) => setState(() => _satisfacao = v)),
        const SizedBox(height: 24),
        _secao('Mensagem anônima (opcional)'),
        TextField(
          controller: _msgCtrl,
          maxLines: 3,
          maxLength: 500,
          decoration: const InputDecoration(
            hintText: 'Compartilhe algo que queira que a empresa saiba (anônimo)...',
          ),
        ),
        const SizedBox(height: 24),

        // ── pedido de ajuda ──────────────────────────────────────────────
        Container(
          decoration: BoxDecoration(
            color: const Color(0xFF102435),
            borderRadius: BorderRadius.circular(16),
            border: Border.all(color: Colors.white12),
          ),
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  const Icon(Icons.volunteer_activism, color: Color(0xFF27D3BE)),
                  const SizedBox(width: 8),
                  Text('Precisa de ajuda?',
                      style: Theme.of(context).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w700)),
                  const Spacer(),
                  Switch(
                    value: _precisaAjuda,
                    onChanged: (v) => setState(() => _precisaAjuda = v),
                    activeThumbColor: const Color(0xFF27D3BE),
                  ),
                ],
              ),
              if (_precisaAjuda) ...[
                const SizedBox(height: 12),
                Text('Tipo de ajuda', style: Theme.of(context).textTheme.labelMedium?.copyWith(color: Colors.white60)),
                const SizedBox(height: 6),
                DropdownButtonFormField<String>(
                  initialValue: _tipoAjuda,
                  dropdownColor: const Color(0xFF102435),
                  decoration: const InputDecoration(contentPadding: EdgeInsets.symmetric(horizontal: 12, vertical: 8)),
                  items: const [
                    DropdownMenuItem(value: 'saude_fisica',  child: Text('Saúde física')),
                    DropdownMenuItem(value: 'saude_mental',  child: Text('Saúde mental / ansiedade')),
                    DropdownMenuItem(value: 'vicio',         child: Text('Dependência / vício')),
                    DropdownMenuItem(value: 'trabalho',      child: Text('Problemas no trabalho')),
                    DropdownMenuItem(value: 'financeiro',    child: Text('Dificuldade financeira')),
                    DropdownMenuItem(value: 'familiar',      child: Text('Problema familiar')),
                    DropdownMenuItem(value: 'outro',         child: Text('Outro')),
                  ],
                  onChanged: (v) => setState(() => _tipoAjuda = v!),
                ),
                const SizedBox(height: 16),
                Container(
                  decoration: BoxDecoration(
                    color: _querContato ? const Color(0xFF0D3020) : Colors.white.withValues(alpha: 0.04),
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(
                      color: _querContato ? const Color(0xFF27D3BE) : Colors.white12,
                    ),
                  ),
                  child: CheckboxListTile(
                    value: _querContato,
                    onChanged: (v) => setState(() => _querContato = v!),
                    activeColor: const Color(0xFF27D3BE),
                    title: const Text('Quero que a empresa entre em contato comigo',
                        style: TextStyle(fontWeight: FontWeight.w600, fontSize: 14)),
                    subtitle: const Text(
                      'Ao marcar esta opção, seu nome será visível apenas para o RH/SST para que possam te apoiar.',
                      style: TextStyle(fontSize: 12, color: Colors.white54),
                    ),
                    controlAffinity: ListTileControlAffinity.leading,
                  ),
                ),
                if (!_querContato)
                  Padding(
                    padding: const EdgeInsets.only(top: 8),
                    child: Row(
                      children: [
                        const Icon(Icons.lock_outline, size: 14, color: Colors.white38),
                        const SizedBox(width: 4),
                        Text('Seu pedido permanecerá anônimo',
                            style: Theme.of(context).textTheme.bodySmall?.copyWith(color: Colors.white38)),
                      ],
                    ),
                  ),
              ],
            ],
          ),
        ),

        const SizedBox(height: 32),
        SizedBox(
          width: double.infinity,
          height: 52,
          child: ElevatedButton(
            onPressed: _enviando ? null : _enviar,
            style: ElevatedButton.styleFrom(
              backgroundColor: const Color(0xFF27D3BE),
              foregroundColor: Colors.black,
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
            ),
            child: _enviando
                ? const SizedBox(width: 22, height: 22, child: CircularProgressIndicator(strokeWidth: 2))
                : const Text('Enviar check-in', style: TextStyle(fontWeight: FontWeight.w800, fontSize: 16)),
          ),
        ),
        const SizedBox(height: 12),
        Center(
          child: Text(
            '🔒 Seus dados são sempre anônimos para a empresa,\nsalvo se você marcar "Quero contato".',
            textAlign: TextAlign.center,
            style: Theme.of(context).textTheme.bodySmall?.copyWith(color: Colors.white38),
          ),
        ),
        const SizedBox(height: 32),
        if (_historico.isNotEmpty) ...[
          _secao('Meus últimos check-ins'),
          _buildHistorico(),
        ],
      ],
    );
  }

  // ── componentes ──────────────────────────────────────────────────────────
  Widget _secao(String titulo) => Padding(
        padding: const EdgeInsets.only(bottom: 12),
        child: Text(titulo,
            style: Theme.of(context).textTheme.titleSmall?.copyWith(
                  color: Colors.white70,
                  fontWeight: FontWeight.w700,
                  letterSpacing: 0.4,
                )),
      );

  Widget _humorSelector() {
    final opcoes = [
      ('otimo',   '😄', 'Ótimo'),
      ('bom',     '🙂', 'Bom'),
      ('regular', '😐', 'Regular'),
      ('ruim',    '😔', 'Ruim'),
      ('pessimo', '😞', 'Péssimo'),
    ];
    return Row(
      mainAxisAlignment: MainAxisAlignment.spaceEvenly,
      children: opcoes.map((op) {
        final selecionado = _humor == op.$1;
        return GestureDetector(
          onTap: () => setState(() => _humor = op.$1),
          child: AnimatedContainer(
            duration: const Duration(milliseconds: 180),
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
            decoration: BoxDecoration(
              color: selecionado ? const Color(0xFF27D3BE).withValues(alpha: 0.15) : Colors.transparent,
              borderRadius: BorderRadius.circular(12),
              border: Border.all(
                color: selecionado ? const Color(0xFF27D3BE) : Colors.white12,
                width: selecionado ? 2 : 1,
              ),
            ),
            child: Column(
              children: [
                Text(op.$2, style: const TextStyle(fontSize: 26)),
                const SizedBox(height: 4),
                Text(op.$3, style: TextStyle(fontSize: 10, color: selecionado ? const Color(0xFF27D3BE) : Colors.white54)),
              ],
            ),
          ),
        );
      }).toList(),
    );
  }

  Widget _sliderItem(String label, int valor, ValueChanged<int> onChanged, {bool inverso = false}) {
    Color cor(int v) {
      if (inverso) {
        // estresse: alto = ruim
        if (v >= 4) return Colors.redAccent;
        if (v == 3) return Colors.orange;
        return const Color(0xFF27D3BE);
      }
      if (v >= 4) return const Color(0xFF27D3BE);
      if (v == 3) return Colors.orange;
      return Colors.redAccent;
    }

    return Padding(
      padding: const EdgeInsets.only(bottom: 16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(label, style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 13)),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 2),
                decoration: BoxDecoration(
                  color: cor(valor).withValues(alpha: 0.15),
                  borderRadius: BorderRadius.circular(20),
                ),
                child: Text('$valor', style: TextStyle(color: cor(valor), fontWeight: FontWeight.w800)),
              ),
            ],
          ),
          SliderTheme(
            data: SliderTheme.of(context).copyWith(
              activeTrackColor: cor(valor),
              thumbColor: cor(valor),
              inactiveTrackColor: Colors.white12,
              overlayColor: cor(valor).withValues(alpha: 0.1),
            ),
            child: Slider(
              value: valor.toDouble(),
              min: 1,
              max: 5,
              divisions: 4,
              onChanged: (v) => onChanged(v.round()),
            ),
          ),
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(inverso ? 'Baixo' : 'Ruim', style: const TextStyle(fontSize: 10, color: Colors.white38)),
              Text(inverso ? 'Alto' : 'Ótimo', style: const TextStyle(fontSize: 10, color: Colors.white38)),
            ],
          ),
        ],
      ),
    );
  }

  Widget _buildHistorico() {
    if (_carregandoHistorico) return const Center(child: CircularProgressIndicator());
    final humorEmoji = {
      'otimo': '😄', 'bom': '🙂', 'regular': '😐', 'ruim': '😔', 'pessimo': '😞',
    };
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: _historico.take(5).map((c) {
        return Container(
          margin: const EdgeInsets.only(bottom: 8),
          padding: const EdgeInsets.all(12),
          decoration: BoxDecoration(
            color: Colors.white.withValues(alpha: 0.04),
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: Colors.white10),
          ),
          child: Row(
            children: [
              Text(humorEmoji[c['humor']] ?? '😐', style: const TextStyle(fontSize: 24)),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(c['humor_label'] ?? '', style: const TextStyle(fontWeight: FontWeight.w700)),
                    Text(c['criado_em'] ?? '', style: const TextStyle(fontSize: 12, color: Colors.white54)),
                  ],
                ),
              ),
              if (c['precisa_ajuda'] == true)
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                  decoration: BoxDecoration(
                    color: Colors.orange.withValues(alpha: 0.15),
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: const Text('Ajuda', style: TextStyle(fontSize: 11, color: Colors.orange)),
                ),
            ],
          ),
        );
      }).toList(),
    );
  }
}
