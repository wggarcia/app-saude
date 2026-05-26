import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;

import '../../config.dart';
import '../../servicos/funcionario_auth_service.dart';

/// Tela de Avaliação Psicossocial NR-01.
/// Carrega questionário ativo e permite ao funcionário responder anonimamente.
class TelaPsicossocial extends StatefulWidget {
  const TelaPsicossocial({super.key});

  @override
  State<TelaPsicossocial> createState() => _TelaPsicossocialState();
}

class _TelaPsicossocialState extends State<TelaPsicossocial> {
  // ── Estado ──────────────────────────────────────────────────────────────
  _Fase _fase = _Fase.carregando;
  Map<String, dynamic>? _avaliacao;
  List<Map<String, dynamic>> _questoes = [];
  Map<int, int> _respostas = {}; // questao_id → valor Likert (1-5)
  String? _erro;
  bool _enviando = false;

  static const _teal = Color(0xFF27D3BE);
  static const _purple = Color(0xFF8B5CF6);
  static const _surface = Color(0xFF102A32);
  static const _amber = Color(0xFFFFB454);

  @override
  void initState() {
    super.initState();
    _carregarAvaliacao();
  }

  Future<Map<String, String>> _headers() async {
    final token = await FuncionarioAuthService.token();
    return {
      'Content-Type': 'application/json',
      if (token != null && token.isNotEmpty)
        'Authorization': 'Bearer $token',
    };
  }

  Future<void> _carregarAvaliacao() async {
    setState(() {
      _fase = _Fase.carregando;
      _erro = null;
    });
    try {
      final headers = await _headers();
      // Busca avaliação ativa para o funcionário
      final r = await http.get(
        Uri.parse('${Config.baseUrl}/api/funcionario/psicossocial/ativa/'),
        headers: headers,
      );

      if (r.statusCode == 404) {
        setState(() => _fase = _Fase.semAvaliacao);
        return;
      }
      if (r.statusCode != 200) {
        setState(() {
          _fase = _Fase.erro;
          _erro = 'Erro ao carregar avaliação (${r.statusCode}).';
        });
        return;
      }

      final data = jsonDecode(r.body) as Map<String, dynamic>;

      if (data['ja_respondeu'] == true) {
        setState(() => _fase = _Fase.jaRespondeu);
        return;
      }

      final questoes = List<Map<String, dynamic>>.from(
          (data['questoes'] ?? []).map((e) => e as Map<String, dynamic>));

      if (questoes.isEmpty) {
        setState(() => _fase = _Fase.semAvaliacao);
        return;
      }

      // Inicializa todas as respostas com valor neutro (3)
      final respostas = <int, int>{};
      for (final q in questoes) {
        respostas[q['id'] as int] = 3;
      }

      setState(() {
        _avaliacao = data;
        _questoes = questoes;
        _respostas = respostas;
        _fase = _Fase.respondendo;
      });
    } catch (e) {
      setState(() {
        _fase = _Fase.erro;
        _erro = e.toString().replaceFirst('Exception: ', '');
      });
    }
  }

  Future<void> _enviar() async {
    // Verifica se todas as questões obrigatórias foram respondidas
    final naoRespondidas = _questoes
        .where((q) =>
            q['obrigatoria'] == true &&
            !_respostas.containsKey(q['id']))
        .length;
    if (naoRespondidas > 0) {
      _snack('Responda todas as questões obrigatórias.', ok: false);
      return;
    }

    setState(() => _enviando = true);
    try {
      final av = _avaliacao!;
      final token = av['link_token']?.toString() ?? '';
      final respostasList = _respostas.entries
          .map((e) => {'questao_id': e.key, 'valor': e.value})
          .toList();

      final r = await http.post(
        Uri.parse('${Config.baseUrl}/api/sst/psicossocial/responder/$token/'),
        headers: const {'Content-Type': 'application/json'},
        body: jsonEncode({'respostas': respostasList}),
      );

      if (!mounted) return;
      if (r.statusCode == 200 || r.statusCode == 201) {
        setState(() => _fase = _Fase.concluido);
      } else {
        final d = jsonDecode(r.body);
        _snack(d['erro'] ?? 'Erro ao enviar respostas.', ok: false);
      }
    } catch (e) {
      _snack('Erro de conexão. Tente novamente.', ok: false);
    } finally {
      if (mounted) setState(() => _enviando = false);
    }
  }

  void _snack(String msg, {required bool ok}) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(msg),
        backgroundColor:
            ok ? _teal.withValues(alpha: 0.9) : Colors.red.shade800,
        behavior: SnackBarBehavior.floating,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
      ),
    );
  }

  // ── Build ────────────────────────────────────────────────────────────────
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Psicossocial — NR-01'),
        actions: [
          if (_fase == _Fase.respondendo)
            IconButton(
              icon: const Icon(Icons.refresh),
              onPressed: _carregarAvaliacao,
              tooltip: 'Recarregar',
            ),
        ],
      ),
      body: switch (_fase) {
        _Fase.carregando => const Center(child: CircularProgressIndicator()),
        _Fase.erro => _buildErro(),
        _Fase.semAvaliacao => _buildSemAvaliacao(),
        _Fase.jaRespondeu => _buildJaRespondeu(),
        _Fase.respondendo => _buildQuestionario(),
        _Fase.concluido => _buildConcluido(),
      },
    );
  }

  // ── Telas de estado ──────────────────────────────────────────────────────
  Widget _buildErro() {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.cloud_off_outlined,
                size: 52, color: Colors.white38),
            const SizedBox(height: 12),
            Text(_erro ?? 'Erro desconhecido.',
                textAlign: TextAlign.center,
                style: const TextStyle(color: Colors.white60)),
            const SizedBox(height: 16),
            FilledButton.icon(
              onPressed: _carregarAvaliacao,
              icon: const Icon(Icons.refresh),
              label: const Text('Tentar novamente'),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildSemAvaliacao() {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: 80,
              height: 80,
              decoration: BoxDecoration(
                color: _purple.withValues(alpha: 0.12),
                borderRadius: BorderRadius.circular(20),
              ),
              child: const Icon(Icons.psychology_outlined,
                  color: _purple, size: 40),
            ),
            const SizedBox(height: 20),
            const Text('Nenhuma avaliação ativa',
                style: TextStyle(
                    color: Colors.white,
                    fontWeight: FontWeight.w800,
                    fontSize: 18)),
            const SizedBox(height: 8),
            const Text(
              'No momento não há questionário psicossocial ativo para responder. '
              'Você será notificado quando uma avaliação for iniciada pela empresa.',
              textAlign: TextAlign.center,
              style: TextStyle(
                  color: Colors.white54, fontSize: 13, height: 1.5),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildJaRespondeu() {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: 80,
              height: 80,
              decoration: BoxDecoration(
                color: _teal.withValues(alpha: 0.12),
                borderRadius: BorderRadius.circular(20),
              ),
              child: const Icon(Icons.check_circle_outline,
                  color: _teal, size: 40),
            ),
            const SizedBox(height: 20),
            const Text('Você já respondeu!',
                style: TextStyle(
                    color: Colors.white,
                    fontWeight: FontWeight.w800,
                    fontSize: 18)),
            const SizedBox(height: 8),
            const Text(
              'Sua participação foi registrada. As respostas são anônimas '
              'e serão usadas para melhorar o ambiente de trabalho.',
              textAlign: TextAlign.center,
              style: TextStyle(
                  color: Colors.white54, fontSize: 13, height: 1.5),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildConcluido() {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              width: 90,
              height: 90,
              decoration: BoxDecoration(
                gradient: LinearGradient(
                  colors: [
                    _purple.withValues(alpha: 0.3),
                    _teal.withValues(alpha: 0.3)
                  ],
                ),
                borderRadius: BorderRadius.circular(22),
              ),
              child: const Icon(Icons.favorite_outline,
                  color: Colors.white, size: 44),
            ),
            const SizedBox(height: 24),
            const Text('Obrigado pela participação!',
                textAlign: TextAlign.center,
                style: TextStyle(
                    color: Colors.white,
                    fontWeight: FontWeight.w900,
                    fontSize: 20)),
            const SizedBox(height: 10),
            const Text(
              'Suas respostas foram enviadas de forma anônima. '
              'Juntos tornamos o ambiente de trabalho mais saudável.',
              textAlign: TextAlign.center,
              style: TextStyle(
                  color: Colors.white60, fontSize: 14, height: 1.55),
            ),
          ],
        ),
      ),
    );
  }

  // ── Questionário ─────────────────────────────────────────────────────────
  Widget _buildQuestionario() {
    final av = _avaliacao!;
    final titulo = (av['titulo'] ?? 'Avaliação Psicossocial').toString();
    final total = _questoes.length;
    final respondidas = _respostas.length;
    final progresso = total > 0 ? respondidas / total : 0.0;

    return Column(
      children: [
        // ── Cabeçalho ──
        Container(
          padding: const EdgeInsets.fromLTRB(16, 12, 16, 10),
          decoration: BoxDecoration(
            color: _surface,
            border: const Border(
                bottom: BorderSide(color: Colors.white10)),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(children: [
                Container(
                  width: 28,
                  height: 28,
                  decoration: BoxDecoration(
                    color: _purple.withValues(alpha: 0.15),
                    borderRadius: BorderRadius.circular(7),
                  ),
                  child: const Icon(Icons.psychology_outlined,
                      color: _purple, size: 16),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: Text(titulo,
                      style: const TextStyle(
                          color: Colors.white,
                          fontWeight: FontWeight.w700,
                          fontSize: 13)),
                ),
                Text('$respondidas/$total',
                    style: const TextStyle(
                        color: Colors.white38, fontSize: 12)),
              ]),
              const SizedBox(height: 8),
              ClipRRect(
                borderRadius: BorderRadius.circular(999),
                child: LinearProgressIndicator(
                  value: progresso,
                  minHeight: 5,
                  backgroundColor: Colors.white10,
                  valueColor:
                      const AlwaysStoppedAnimation(_purple),
                ),
              ),
              const SizedBox(height: 6),
              const Text(
                '🔒 Anônimo — suas respostas são confidenciais',
                style:
                    TextStyle(color: Colors.white38, fontSize: 11),
              ),
            ],
          ),
        ),

        // ── Lista de questões ──
        Expanded(
          child: ListView.builder(
            padding: const EdgeInsets.fromLTRB(16, 14, 16, 100),
            itemCount: _questoes.length,
            itemBuilder: (ctx, i) =>
                _buildQuestao(_questoes[i], i),
          ),
        ),

        // ── Botão enviar (fixo na base) ──
        Container(
          padding: const EdgeInsets.fromLTRB(16, 10, 16, 24),
          decoration: const BoxDecoration(
            color: Color(0xFF0A1820),
            border:
                Border(top: BorderSide(color: Colors.white10)),
          ),
          child: SafeArea(
            top: false,
            child: FilledButton(
              style: FilledButton.styleFrom(
                backgroundColor: _purple,
                minimumSize: const Size.fromHeight(50),
                shape: RoundedRectangleBorder(
                    borderRadius: BorderRadius.circular(14)),
              ),
              onPressed: _enviando ? null : _enviar,
              child: _enviando
                  ? const SizedBox(
                      width: 20,
                      height: 20,
                      child: CircularProgressIndicator(
                          strokeWidth: 2,
                          color: Colors.white))
                  : const Text('Enviar respostas',
                      style: TextStyle(
                          fontWeight: FontWeight.w900,
                          fontSize: 15)),
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildQuestao(Map<String, dynamic> q, int index) {
    final id = q['id'] as int;
    final texto =
        (q['texto'] ?? q['enunciado'] ?? 'Questão').toString();
    final obrigatoria = q['obrigatoria'] == true;
    final valor = _respostas[id] ?? 3;

    // Labels da escala Likert
    const likertLabels = {
      1: 'Nunca',
      2: 'Raramente',
      3: 'Às vezes',
      4: 'Frequentemente',
      5: 'Sempre',
    };

    final cor = valor <= 2
        ? _teal
        : valor == 3
            ? _amber
            : const Color(0xFFFF6B6B);

    return Container(
      margin: const EdgeInsets.only(bottom: 14),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: _surface,
        borderRadius: BorderRadius.circular(16),
        border: Border(
          left: BorderSide(
              color: _purple.withValues(alpha: 0.35), width: 3),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Container(
                width: 22,
                height: 22,
                decoration: BoxDecoration(
                  color: _purple.withValues(alpha: 0.15),
                  borderRadius: BorderRadius.circular(6),
                ),
                child: Center(
                  child: Text('${index + 1}',
                      style: const TextStyle(
                          color: _purple,
                          fontSize: 10,
                          fontWeight: FontWeight.w800)),
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: Text(
                  texto + (obrigatoria ? ' *' : ''),
                  style: const TextStyle(
                      color: Colors.white,
                      fontWeight: FontWeight.w600,
                      fontSize: 14,
                      height: 1.4),
                ),
              ),
            ],
          ),
          const SizedBox(height: 14),

          // ── Slider Likert ──
          SliderTheme(
            data: SliderTheme.of(context).copyWith(
              activeTrackColor: cor,
              inactiveTrackColor: Colors.white10,
              thumbColor: cor,
              overlayColor: cor.withValues(alpha: 0.15),
              trackHeight: 4,
              thumbShape:
                  const RoundSliderThumbShape(enabledThumbRadius: 8),
            ),
            child: Slider(
              value: valor.toDouble(),
              min: 1,
              max: 5,
              divisions: 4,
              onChanged: (v) {
                setState(() => _respostas[id] = v.round());
              },
            ),
          ),

          // ── Labels extremos ──
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 4),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                const Text('Nunca',
                    style:
                        TextStyle(color: Colors.white38, fontSize: 10)),
                Container(
                  padding: const EdgeInsets.symmetric(
                      horizontal: 10, vertical: 3),
                  decoration: BoxDecoration(
                    color: cor.withValues(alpha: 0.13),
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: Text(
                    likertLabels[valor] ?? '',
                    style: TextStyle(
                        color: cor,
                        fontWeight: FontWeight.w800,
                        fontSize: 11),
                  ),
                ),
                const Text('Sempre',
                    style:
                        TextStyle(color: Colors.white38, fontSize: 10)),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

enum _Fase {
  carregando,
  erro,
  semAvaliacao,
  jaRespondeu,
  respondendo,
  concluido,
}
