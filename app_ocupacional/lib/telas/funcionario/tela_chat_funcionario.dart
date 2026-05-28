import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../servicos/funcionario_auth_service.dart';
import '../../servicos/funcionario_sst_service.dart';

/// Chat direto entre funcionário e empresa/RH — polling a cada 8 segundos.
class TelaChatFuncionario extends StatefulWidget {
  const TelaChatFuncionario({super.key});

  @override
  State<TelaChatFuncionario> createState() => _TelaChatFuncionarioState();
}

class _TelaChatFuncionarioState extends State<TelaChatFuncionario> {
  // ── Cores ──────────────────────────────────────────────────────────────────
  static const _teal    = Color(0xFF27D3BE);
  static const _surface = Color(0xFF102A32);
  static const _bg      = Color(0xFF071820);

  // ── Estado ─────────────────────────────────────────────────────────────────
  String? _aliasCodigo;   // sst-{func_id}
  List<dynamic> _msgs = const [];
  bool _loadingInicial = true;
  bool _enviando = false;
  String? _erro;
  String? _ultimaData;    // para polling incremental

  final _scroll  = ScrollController();
  final _input   = TextEditingController();
  final _focus   = FocusNode();
  Timer? _timer;

  // ──────────────────────────────────────────────────────────────────────────

  @override
  void initState() {
    super.initState();
    _inicializar();
  }

  @override
  void dispose() {
    _timer?.cancel();
    _scroll.dispose();
    _input.dispose();
    _focus.dispose();
    super.dispose();
  }

  Future<void> _inicializar() async {
    final funcId = await FuncionarioAuthService.funcId();
    if (funcId == null) {
      if (!mounted) return;
      setState(() {
        _erro = 'Não foi possível identificar seu cadastro.\nFaça logout e entre novamente.';
        _loadingInicial = false;
      });
      return;
    }
    _aliasCodigo = 'sst-$funcId';
    await _carregarMensagens(inicial: true);
    _timer = Timer.periodic(const Duration(seconds: 8), (_) => _carregarMensagens());
  }

  Future<void> _carregarMensagens({bool inicial = false}) async {
    if (_aliasCodigo == null) return;
    try {
      final data = await FuncionarioSstService.chatMensagens(
        _aliasCodigo!,
        desde: inicial ? null : _ultimaData,
      );
      if (!mounted) return;

      final novas = (data['mensagens'] as List? ?? []);

      if (inicial) {
        setState(() {
          _msgs = novas;
          _loadingInicial = false;
          _erro = null;
        });
      } else if (novas.isNotEmpty) {
        setState(() {
          // Adiciona apenas mensagens novas (evita duplicatas)
          final ids = _msgs.map((m) => (m as Map)['id']).toSet();
          final paraAdicionar = novas.where((m) => !ids.contains((m as Map)['id'])).toList();
          if (paraAdicionar.isNotEmpty) {
            _msgs = [..._msgs, ...paraAdicionar];
          }
        });
      }

      // Guarda timestamp da última mensagem para polling incremental
      if (_msgs.isNotEmpty) {
        _ultimaData = (_msgs.last as Map)['criado_em']?.toString();
      }

      // Scroll para o fim se já estava perto do fim
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (_scroll.hasClients &&
            _scroll.position.maxScrollExtent - _scroll.offset < 200) {
          _scroll.animateTo(
            _scroll.position.maxScrollExtent,
            duration: const Duration(milliseconds: 300),
            curve: Curves.easeOut,
          );
        }
      });
    } catch (e) {
      if (inicial && mounted) {
        setState(() {
          _erro = e.toString().replaceFirst('Exception: ', '');
          _loadingInicial = false;
        });
      }
    }
  }

  Future<void> _enviar() async {
    final texto = _input.text.trim();
    if (texto.isEmpty || _aliasCodigo == null || _enviando) return;

    setState(() => _enviando = true);
    _input.clear();

    try {
      final data = await FuncionarioSstService.chatEnviar(_aliasCodigo!, texto);
      if (!mounted) return;
      final msg = data['mensagem'];
      if (msg != null) {
        setState(() => _msgs = [..._msgs, msg]);
        _ultimaData = (msg as Map)['criado_em']?.toString();
        // Scroll para o fim após envio
        WidgetsBinding.instance.addPostFrameCallback((_) {
          if (_scroll.hasClients) {
            _scroll.animateTo(
              _scroll.position.maxScrollExtent,
              duration: const Duration(milliseconds: 300),
              curve: Curves.easeOut,
            );
          }
        });
      }
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Erro ao enviar: ${e.toString().replaceFirst("Exception: ", "")}'),
          backgroundColor: Colors.redAccent,
          behavior: SnackBarBehavior.floating,
        ),
      );
      // Restaura o texto se falhou
      _input.text = texto;
    } finally {
      if (mounted) setState(() => _enviando = false);
    }
  }

  // ── Build ──────────────────────────────────────────────────────────────────

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: _bg,
      body: Column(
        children: [
          // ── Banner de contexto ─────────────────────────────────────────────
          Container(
            width: double.infinity,
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
            color: _surface,
            child: Row(
              children: [
                const CircleAvatar(
                  radius: 16,
                  backgroundColor: Color(0xFF27D3BE),
                  child: Icon(Icons.business_outlined, size: 16, color: Color(0xFF071820)),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text('RH / Segurança do Trabalho',
                          style: TextStyle(
                              fontWeight: FontWeight.w700,
                              fontSize: 13,
                              color: Colors.white)),
                      Text(
                        _aliasCodigo != null ? 'Conversa direta segura' : 'Carregando...',
                        style: const TextStyle(fontSize: 11, color: Colors.white38),
                      ),
                    ],
                  ),
                ),
                IconButton(
                  icon: const Icon(Icons.refresh, size: 18),
                  color: Colors.white38,
                  onPressed: () => _carregarMensagens(inicial: true),
                  tooltip: 'Atualizar',
                ),
              ],
            ),
          ),

          // ── Lista de mensagens ─────────────────────────────────────────────
          Expanded(child: _buildMensagens()),

          // ── Input bar ─────────────────────────────────────────────────────
          _buildInput(),
        ],
      ),
    );
  }

  Widget _buildMensagens() {
    if (_loadingInicial) {
      return const Center(child: CircularProgressIndicator());
    }

    if (_erro != null) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.wifi_off_outlined, size: 48, color: Colors.white38),
              const SizedBox(height: 12),
              Text(_erro!, textAlign: TextAlign.center,
                  style: const TextStyle(color: Colors.white60)),
              const SizedBox(height: 16),
              FilledButton.icon(
                onPressed: () => _carregarMensagens(inicial: true),
                icon: const Icon(Icons.refresh),
                label: const Text('Tentar novamente'),
              ),
            ],
          ),
        ),
      );
    }

    if (_msgs.isEmpty) {
      return const Center(
        child: Padding(
          padding: EdgeInsets.all(32),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(Icons.chat_bubble_outline, size: 56, color: Colors.white12),
              SizedBox(height: 16),
              Text(
                'Nenhuma mensagem ainda',
                style: TextStyle(fontSize: 16, color: Colors.white38),
              ),
              SizedBox(height: 8),
              Text(
                'Envie uma mensagem para o RH ou\nSegurança do Trabalho da sua empresa.',
                textAlign: TextAlign.center,
                style: TextStyle(fontSize: 12, color: Colors.white24),
              ),
            ],
          ),
        ),
      );
    }

    return ListView.builder(
      controller: _scroll,
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 16),
      itemCount: _msgs.length,
      itemBuilder: (_, i) {
        final msg = _msgs[i] as Map<String, dynamic>;
        final origem = msg['origem']?.toString() ?? '';
        final isFunc = origem == 'colaborador'; // funcionário → 'colaborador'
        final texto  = msg['texto']?.toString() ?? '';
        final hora   = _formatHora(msg['criado_em']?.toString() ?? '');

        return _BubbleMensagem(
          texto: texto,
          hora: hora,
          isEmployee: isFunc,
          teal: _teal,
        );
      },
    );
  }

  Widget _buildInput() {
    return Container(
      padding: EdgeInsets.fromLTRB(
        12, 8, 12, MediaQuery.of(context).padding.bottom + 8),
      decoration: const BoxDecoration(
        color: _surface,
        border: Border(top: BorderSide(color: Colors.white12)),
      ),
      child: Row(
        children: [
          Expanded(
            child: TextField(
              controller: _input,
              focusNode: _focus,
              maxLines: 4,
              minLines: 1,
              textCapitalization: TextCapitalization.sentences,
              style: const TextStyle(color: Colors.white, fontSize: 14),
              decoration: InputDecoration(
                hintText: 'Mensagem para o RH...',
                hintStyle: const TextStyle(color: Colors.white38, fontSize: 14),
                contentPadding:
                    const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                filled: true,
                fillColor: const Color(0xFF0B2028),
                border: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(24),
                  borderSide: BorderSide.none,
                ),
                enabledBorder: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(24),
                  borderSide: BorderSide.none,
                ),
                focusedBorder: OutlineInputBorder(
                  borderRadius: BorderRadius.circular(24),
                  borderSide:
                      const BorderSide(color: _teal, width: 1.5),
                ),
              ),
              onSubmitted: (_) => _enviar(),
            ),
          ),
          const SizedBox(width: 8),
          _enviando
              ? const SizedBox(
                  width: 44,
                  height: 44,
                  child: Center(
                      child: SizedBox(
                          width: 20,
                          height: 20,
                          child: CircularProgressIndicator(strokeWidth: 2))),
                )
              : Material(
                  color: _teal,
                  borderRadius: BorderRadius.circular(24),
                  child: InkWell(
                    borderRadius: BorderRadius.circular(24),
                    onTap: _enviar,
                    child: const Padding(
                      padding: EdgeInsets.all(10),
                      child: Icon(Icons.send_rounded,
                          color: Color(0xFF041018), size: 22),
                    ),
                  ),
                ),
        ],
      ),
    );
  }

  String _formatHora(String iso) {
    try {
      final dt = DateTime.parse(iso).toLocal();
      final h = dt.hour.toString().padLeft(2, '0');
      final m = dt.minute.toString().padLeft(2, '0');
      final hoje = DateTime.now();
      if (dt.day == hoje.day && dt.month == hoje.month && dt.year == hoje.year) {
        return '$h:$m';
      }
      return '${dt.day}/${dt.month} $h:$m';
    } catch (_) {
      return '';
    }
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Bolha de mensagem
// ─────────────────────────────────────────────────────────────────────────────
class _BubbleMensagem extends StatelessWidget {
  const _BubbleMensagem({
    required this.texto,
    required this.hora,
    required this.isEmployee,
    required this.teal,
  });

  final String texto;
  final String hora;
  final bool   isEmployee; // true = funcionário (direita), false = empresa (esquerda)
  final Color  teal;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 3),
      child: Row(
        mainAxisAlignment:
            isEmployee ? MainAxisAlignment.end : MainAxisAlignment.start,
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          if (!isEmployee)
            const Padding(
              padding: EdgeInsets.only(right: 6, bottom: 4),
              child: CircleAvatar(
                radius: 14,
                backgroundColor: Color(0xFF27D3BE),
                child: Icon(Icons.business_outlined,
                    size: 14, color: Color(0xFF071820)),
              ),
            ),
          Flexible(
            child: GestureDetector(
              onLongPress: () {
                Clipboard.setData(ClipboardData(text: texto));
                ScaffoldMessenger.of(context).showSnackBar(
                  const SnackBar(
                    content: Text('Mensagem copiada'),
                    duration: Duration(seconds: 1),
                    behavior: SnackBarBehavior.floating,
                  ),
                );
              },
              child: Container(
                padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 9),
                decoration: BoxDecoration(
                  color: isEmployee
                      ? teal.withValues(alpha: 0.85)
                      : const Color(0xFF0F2D3A),
                  borderRadius: BorderRadius.only(
                    topLeft: const Radius.circular(18),
                    topRight: const Radius.circular(18),
                    bottomLeft: Radius.circular(isEmployee ? 18 : 4),
                    bottomRight: Radius.circular(isEmployee ? 4 : 18),
                  ),
                  border: isEmployee
                      ? null
                      : Border.all(color: Colors.white12),
                ),
                child: Column(
                  crossAxisAlignment: isEmployee
                      ? CrossAxisAlignment.end
                      : CrossAxisAlignment.start,
                  children: [
                    Text(
                      texto,
                      style: TextStyle(
                        color: isEmployee
                            ? const Color(0xFF041018)
                            : Colors.white,
                        fontSize: 14,
                        height: 1.4,
                        fontWeight: isEmployee
                            ? FontWeight.w600
                            : FontWeight.normal,
                      ),
                    ),
                    const SizedBox(height: 3),
                    Text(
                      hora,
                      style: TextStyle(
                        fontSize: 10,
                        color: isEmployee
                            ? const Color(0xFF041018).withValues(alpha: 0.55)
                            : Colors.white38,
                      ),
                    ),
                  ],
                ),
              ),
            ),
          ),
          if (isEmployee)
            const Padding(
              padding: EdgeInsets.only(left: 6, bottom: 4),
              child: CircleAvatar(
                radius: 14,
                backgroundColor: Color(0xFF1A3D4A),
                child: Icon(Icons.person_outline,
                    size: 14, color: Color(0xFF27D3BE)),
              ),
            ),
        ],
      ),
    );
  }
}
