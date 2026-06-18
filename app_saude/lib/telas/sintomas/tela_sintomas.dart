import 'package:flutter/material.dart';

import '../../servicos/location_service.dart';
import '../../servicos/public_api_service.dart';
import '../../servicos/regiao_base_service.dart';
import '../../tela_resultado.dart';
import '../fontes/tela_fontes.dart';

// ─── Modelo de pergunta de sintoma ────────────────────────────────────────────
class _PerguntaSintoma {
  const _PerguntaSintoma({
    required this.key,
    required this.pergunta,
    required this.dica,
    this.emoji = '',
    this.isUrgencia = false,
    this.followup, // 'febre' | 'articular'
  });
  final String key;
  final String pergunta;
  final String dica;
  final String emoji;
  final bool isUrgencia;
  final String? followup;
}

// ─── Perguntas de sintomas — ordem clínica neutra, sem nome de doença ────────
// Agrupamento por tipo (geral → respiratório → gastrointestinal → urgência)
// mas SEM rótulo de doença. Elimina o viés de ancoragem.
const _perguntas = [
  _PerguntaSintoma(
    key: 'febre',
    pergunta: 'Você tem ou teve febre?',
    dica: 'Temperatura acima de 37,5°C nas últimas 24 horas',
    emoji: '🌡️',
    followup: 'febre',
  ),
  _PerguntaSintoma(
    key: 'cansaco',
    pergunta: 'Sente cansaço intenso?',
    dica: 'Fadiga que dificulta suas atividades normais',
    emoji: '😴',
  ),
  _PerguntaSintoma(
    key: 'dor_corpo',
    pergunta: 'Tem dor no corpo?',
    dica: 'Dores musculares generalizadas — mialgia',
    emoji: '💪',
  ),
  _PerguntaSintoma(
    key: 'dor_cabeca',
    pergunta: 'Tem dor de cabeça?',
    dica: 'Cefaleia — pode ser intensa ou persistente',
    emoji: '🤕',
  ),
  _PerguntaSintoma(
    key: 'calafrios',
    pergunta: 'Teve calafrios ou tremores com sensação de frio?',
    dica: 'Mesmo com febre — sensação de frio intenso com tremores',
    emoji: '🥶',
  ),
  _PerguntaSintoma(
    key: 'sudorese',
    pergunta: 'Tem suado muito?',
    dica: 'Sudorese intensa, especialmente à noite ou após calafrios',
    emoji: '💧',
  ),
  _PerguntaSintoma(
    key: 'tosse',
    pergunta: 'Tem tosse?',
    dica: 'Seca, com catarro ou persistente',
    emoji: '🫁',
  ),
  _PerguntaSintoma(
    key: 'falta_ar',
    pergunta: 'Tem falta de ar?',
    dica: 'Dificuldade para respirar — mesmo em repouso ou ao menor esforço',
    emoji: '💨',
  ),
  _PerguntaSintoma(
    key: 'dor_garganta',
    pergunta: 'Tem dor de garganta?',
    dica: 'Ao engolir ou em repouso',
    emoji: '😮',
  ),
  _PerguntaSintoma(
    key: 'coriza',
    pergunta: 'Está com coriza?',
    dica: 'Nariz escorrendo ou entupido, espirros frequentes',
    emoji: '🤧',
  ),
  _PerguntaSintoma(
    key: 'perda_olfato_paladar',
    pergunta: 'Perdeu o olfato ou o paladar?',
    dica: 'Não sente cheiro ou sabor como antes',
    emoji: '👃',
  ),
  _PerguntaSintoma(
    key: 'dor_articular',
    pergunta: 'Tem dor nas articulações?',
    dica: 'Joelhos, tornozelos, pulsos, dedos',
    emoji: '🦴',
    followup: 'articular',
  ),
  _PerguntaSintoma(
    key: 'exantema',
    pergunta: 'Surgiram manchas ou vermelhidão na pele?',
    dica: 'Rash, bolinhas, manchas espalhadas — pode coçar',
    emoji: '🔴',
  ),
  _PerguntaSintoma(
    key: 'conjuntivite',
    pergunta: 'Os olhos estão vermelhos ou irritados?',
    dica: 'Hiperemia ocular — sem secreção purulenta amarelada',
    emoji: '👁️',
  ),
  _PerguntaSintoma(
    key: 'vomito_nausea',
    pergunta: 'Tem vômito ou náusea?',
    dica: 'Enjoo persistente ou episódios de vômito',
    emoji: '🤢',
  ),
  _PerguntaSintoma(
    key: 'diarreia',
    pergunta: 'Tem diarreia?',
    dica: 'Mais de 3 evacuações líquidas por dia',
    emoji: '🚽',
  ),
  _PerguntaSintoma(
    key: 'dor_abdominal',
    pergunta: 'Tem dor na barriga?',
    dica: 'Dor abdominal persistente ou em cólicas',
    emoji: '🫄',
  ),
  _PerguntaSintoma(
    key: 'ictericia',
    pergunta: 'A pele ou os olhos ficaram amarelados?',
    dica: 'Icterícia — coloração amarela na pele ou no branco dos olhos',
    emoji: '🟡',
  ),
  _PerguntaSintoma(
    key: 'manchas_hemorragicas',
    pergunta: 'Surgiram manchas roxas ou sangramentos?',
    dica: 'Petéquias, hematomas espontâneos ou sangramento sem corte',
    emoji: '🟣',
    isUrgencia: true,
  ),
  _PerguntaSintoma(
    key: 'rigidez_nuca',
    pergunta: 'Tem dificuldade de dobrar o pescoço?',
    dica: 'Rigidez — dificuldade de encostar o queixo no peito',
    emoji: '🚨',
    isUrgencia: true,
  ),
];

// ─── Perguntas de anamnese epidemiológica ────────────────────────────────────
enum _TipoAnamnese { simNao, dias }

class _ItemAnamnese {
  const _ItemAnamnese({
    required this.tipo,
    required this.pergunta,
    required this.dica,
    this.emoji = '',
  });
  final _TipoAnamnese tipo;
  final String pergunta;
  final String dica;
  final String emoji;
}

const _anamneseItems = [
  _ItemAnamnese(
    tipo: _TipoAnamnese.dias,
    pergunta: 'Há quantos dias com esses sintomas?',
    dica: 'Desde o primeiro sinal — mesmo que leve',
    emoji: '📅',
  ),
  _ItemAnamnese(
    tipo: _TipoAnamnese.simNao,
    pergunta: 'O início foi repentino?',
    dica: 'Abrupto (do nada) ou gradual (ao longo de dias)',
    emoji: '⚡',
  ),
  _ItemAnamnese(
    tipo: _TipoAnamnese.simNao,
    pergunta: 'Viajou para Amazônia, pantanal ou zona de mata?',
    dica: 'Nas últimas 4 semanas',
    emoji: '🌿',
  ),
  _ItemAnamnese(
    tipo: _TipoAnamnese.simNao,
    pergunta: 'Teve contato com água de enchente ou esgoto?',
    dica: 'Wading, limpeza pós-enchente, rua alagada',
    emoji: '🌊',
  ),
  _ItemAnamnese(
    tipo: _TipoAnamnese.simNao,
    pergunta: 'Teve contato com ratos ou animais silvestres?',
    dica: 'Fezes, urina ou toque — rural ou urbano',
    emoji: '🐭',
  ),
  _ItemAnamnese(
    tipo: _TipoAnamnese.simNao,
    pergunta: 'Esteve próximo de alguém com doença confirmada?',
    dica: 'Convívio doméstico ou contato próximo nas últimas 2 semanas',
    emoji: '👥',
  ),
  _ItemAnamnese(
    tipo: _TipoAnamnese.simNao,
    pergunta: 'Está vacinado para Febre Amarela?',
    dica: 'Vacina em dia reduz probabilidade quase a zero',
    emoji: '💉',
  ),
  _ItemAnamnese(
    tipo: _TipoAnamnese.simNao,
    pergunta: 'Tem diabetes?',
    dica: 'Diabetes tipo 1 ou tipo 2, mesmo controlada com medicamento',
    emoji: '🩸',
  ),
  _ItemAnamnese(
    tipo: _TipoAnamnese.simNao,
    pergunta: 'Tem pressão alta (hipertensão)?',
    dica: 'Mesmo que esteja tomando remédio e esteja controlada',
    emoji: '💊',
  ),
  _ItemAnamnese(
    tipo: _TipoAnamnese.simNao,
    pergunta: 'Tem doença pulmonar, asma ou DPOC?',
    dica: 'Asma, bronquite crônica, enfisema ou qualquer doença respiratória crônica',
    emoji: '🫁',
  ),
  _ItemAnamnese(
    tipo: _TipoAnamnese.simNao,
    pergunta: 'Tem imunossupressão ou faz tratamento oncológico?',
    dica: 'Quimioterapia, transplante, HIV, uso de corticoide por longa data',
    emoji: '🏥',
  ),
];

// ─── Tela principal ───────────────────────────────────────────────────────────
class TelaSintomas extends StatefulWidget {
  const TelaSintomas({super.key, this.onSintomasEnviados});

  final VoidCallback? onSintomasEnviados;

  @override
  State<TelaSintomas> createState() => _TelaSintomasState();
}

class _TelaSintomasState extends State<TelaSintomas> {
  // ── Fase: 0=sintomas, 1=anamnese ──
  int _fase = 0;
  int _index = 0;

  // null = aguardando followup de intensidade
  String? _followupAtivo; // 'febre' | 'articular'

  // Após o último item de anamnese → pronto para enviar
  bool _concluido = false;

  // ── Estado dos sintomas (todos inicializam false) ──
  final Map<String, bool> _sintomas = {
    for (final p in _perguntas) p.key: false,
  };
  String? _intensidadeFebre;
  String? _intensidadeArticular;

  // ── Estado da anamnese ──
  int? _diasSintomas;
  bool? _inicioAbrupto;
  bool? _viagemAreaEndemica;
  bool? _exposicaoAguaEnchente;
  bool? _contatoRoedores;
  bool? _contatoConfirmado;
  bool? _vacinadoFebreAmarela;
  bool? _temDiabetes;
  bool? _temHipertensao;
  bool? _temDoencaPulmonar;
  bool? _temImunossupressao;

  // Computed: true se qualquer condição crônica foi marcada Sim
  bool? get _temComorbidade {
    final respostas = [_temDiabetes, _temHipertensao, _temDoencaPulmonar, _temImunossupressao];
    if (respostas.every((r) => r == null)) return null;
    return respostas.any((r) => r == true);
  }

  // ── Envio ──
  bool _loading = false;
  Map<String, dynamic>? _lastResult;

  // ── Cooldown: 1 envio por 24 h ──
  Duration? _cooldown;

  // ── Totais ──
  int get _totalSintomas => _sintomas.values.where((v) => v).length;

  // ── Progresso global ──
  int get _progressoAtual =>
      _fase == 0 ? _index : (_perguntas.length + _index);
  int get _progressoTotal => _perguntas.length + _anamneseItems.length;

  // ── Limpar tudo ──
  void _limparTudo() {
    setState(() {
      for (final key in _sintomas.keys) {
        _sintomas[key] = false;
      }
      _intensidadeFebre = null;
      _intensidadeArticular = null;
      _diasSintomas = null;
      _inicioAbrupto = null;
      _viagemAreaEndemica = null;
      _exposicaoAguaEnchente = null;
      _contatoRoedores = null;
      _contatoConfirmado = null;
      _vacinadoFebreAmarela = null;
      _temDiabetes = null;
      _temHipertensao = null;
      _temDoencaPulmonar = null;
      _temImunossupressao = null;
      _lastResult = null;
      _fase = 0;
      _index = 0;
      _followupAtivo = null;
      _concluido = false;
    });
  }

  // ── Navegar para próxima pergunta ──
  void _avancar() {
    setState(() {
      _followupAtivo = null;
      if (_fase == 0) {
        if (_index < _perguntas.length - 1) {
          _index++;
        } else {
          _fase = 1;
          _index = 0;
        }
      } else {
        if (_index < _anamneseItems.length - 1) {
          _index++;
        } else {
          _concluido = true;
        }
      }
    });
  }

  // ── Navegar para pergunta anterior ──
  void _voltar() {
    setState(() {
      _followupAtivo = null;
      if (_concluido) {
        _concluido = false;
        _fase = 1;
        _index = _anamneseItems.length - 1;
        return;
      }
      if (_index > 0) {
        _index--;
      } else if (_fase == 1) {
        _fase = 0;
        _index = _perguntas.length - 1;
      }
    });
  }

  // ── Responder sintoma (Sim/Não) ──
  void _responderSintoma(bool valor) async {
    final pergunta = _perguntas[_index];
    _sintomas[pergunta.key] = valor;

    // Sintoma de urgência com Sim → mostrar alerta antes de continuar
    if (valor && pergunta.isUrgencia) {
      await _mostrarAlertaUrgencia(pergunta.key);
      return;
    }

    // Febre sim → pedir intensidade
    if (valor && pergunta.followup != null) {
      setState(() => _followupAtivo = pergunta.followup);
      return;
    }

    // Caso contrário avançar direto
    setState(() {});
    await Future.delayed(const Duration(milliseconds: 120));
    _avancar();
  }

  // ── Selecionar intensidade ──
  void _selecionarIntensidade(String tipo, String valor) async {
    setState(() {
      if (tipo == 'febre') {
        _intensidadeFebre = valor;
      } else {
        _intensidadeArticular = valor;
      }
      _followupAtivo = null;
    });
    await Future.delayed(const Duration(milliseconds: 120));
    _avancar();
  }

  // ── Responder anamnese ──
  void _responderAnamnese(dynamic valor) async {
    setState(() {
      switch (_index) {
        case 0:
          _diasSintomas = valor as int?;
        case 1:
          _inicioAbrupto = valor as bool?;
        case 2:
          _viagemAreaEndemica = valor as bool?;
        case 3:
          _exposicaoAguaEnchente = valor as bool?;
        case 4:
          _contatoRoedores = valor as bool?;
        case 5:
          _contatoConfirmado = valor as bool?;
        case 6:
          _vacinadoFebreAmarela = valor as bool?;
        case 7:
          _temDiabetes = valor as bool?;
        case 8:
          _temHipertensao = valor as bool?;
        case 9:
          _temDoencaPulmonar = valor as bool?;
        case 10:
          _temImunossupressao = valor as bool?;
      }
    });
    if (valor != null) {
      await Future.delayed(const Duration(milliseconds: 150));
      _avancar();
    }
  }

  dynamic _valorAnamnese(int idx) {
    return switch (idx) {
      0 => _diasSintomas,
      1 => _inicioAbrupto,
      2 => _viagemAreaEndemica,
      3 => _exposicaoAguaEnchente,
      4 => _contatoRoedores,
      5 => _contatoConfirmado,
      6 => _vacinadoFebreAmarela,
      7 => _temDiabetes,
      8 => _temHipertensao,
      9 => _temDoencaPulmonar,
      10 => _temImunossupressao,
      _ => null,
    };
  }

  // ── Alerta de urgência ──
  Future<void> _mostrarAlertaUrgencia(String campo) async {
    final isMeningite = campo == 'rigidez_nuca';
    final titulo = isMeningite
        ? 'Sinal de emergência detectado'
        : 'Sinal de urgência detectado';
    final mensagem = isMeningite
        ? 'Rigidez na nuca pode indicar MENINGITE.\n\nLigue 192 (SAMU) ou vá ao pronto-socorro imediatamente.\n\nDeseja continuar com o registro para o radar epidemiológico?'
        : 'Manchas roxas ou sangramento espontâneo podem indicar quadro grave.\n\nProcure atendimento médico urgente.\n\nDeseja continuar com o registro epidemiológico?';

    if (!mounted) return;
    final continuar = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text(titulo),
        content: Text(mensagem),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('Cancelar'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Continuar registro'),
          ),
        ],
      ),
    );
    if (!mounted) return;

    if (continuar == true) {
      final p = _perguntas[_index];
      if (p.followup != null) {
        setState(() => _followupAtivo = p.followup);
      } else {
        _avancar();
      }
    } else {
      // Desfazer o "sim" se o usuário cancelar
      setState(() => _sintomas[campo] = false);
    }
  }

  // ── Enviar ──
  Future<void> _enviar() async {
    if (_totalSintomas == 0) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
            content: Text('Responda ao menos um sintoma como Sim.')),
      );
      return;
    }

    setState(() => _loading = true);
    try {
      final location = await _resolverLocalizacao();
      if (location == null) return;

      final result = await PublicApiService.enviarSintomas(
        sintomas: Map<String, bool>.from(_sintomas),
        latitude: location.latitude,
        longitude: location.longitude,
        locationSource: location.source,
        intensidadeFebre: _intensidadeFebre,
        intensidadeArticular: _intensidadeArticular,
        diasSintomas: _diasSintomas,
        inicioAbrupto: _inicioAbrupto,
        viagemAreaEndemica: _viagemAreaEndemica,
        exposicaoAguaEnchente: _exposicaoAguaEnchente,
        contatoRoedores: _contatoRoedores,
        contatoConfirmado: _contatoConfirmado,
        vacinadoFebreAmarela: _vacinadoFebreAmarela,
        temComorbidade: _temComorbidade,
      );

      final local = result['local'] as Map<String, dynamic>? ?? {};
      await RegiaoBaseService.registrarObservacao(
        local: local,
        latitude: location.latitude,
        longitude: location.longitude,
      );
      await RegiaoBaseService.salvarModoMonitoramento('atual');

      if (!mounted) return;
      setState(() => _lastResult = result);

      final cidadao = result['cidadao'] as Map<String, dynamic>?;

      if (cidadao != null) {
        await Navigator.of(context).push(
          MaterialPageRoute(
            builder: (_) => TelaResultado(cidadao: cidadao, local: local),
          ),
        );
      } else {
        final jaConsiderado = result['status'] == 'ja_considerado';
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(jaConsiderado
                ? 'Envio recebido. Para proteger o mapa, repetições recentes entram como revisão.'
                : 'Sintomas enviados com segurança. Obrigado por contribuir.'),
            duration: const Duration(seconds: 5),
          ),
        );
      }
      widget.onSintomasEnviados?.call();
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(e.toString().replaceFirst('Exception: ', ''))),
      );
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<LocationSnapshot?> _resolverLocalizacao() async {
    try {
      return await LocationService.getCurrentLocationForSubmission();
    } catch (e) {
      final base = await RegiaoBaseService.obterRegiaoBase();
      final fallback = await LocationService.getBestEffortLocation(
        fallbackRegion: base,
      );
      if (mounted && fallback.source != 'current') {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text(
              'GPS atual instável. Envio registrado com melhor região disponível.',
            ),
            duration: Duration(seconds: 5),
          ),
        );
      }
      return fallback;
    }
  }

  @override
  void initState() {
    super.initState();
    PublicApiService.cooldownRestante().then((d) {
      if (mounted && d != null) setState(() => _cooldown = d);
    });
  }

  String _formatarCooldown(Duration d) {
    final dias = d.inDays;
    final horas = d.inHours % 24;
    final minutos = d.inMinutes % 60;
    if (dias > 0) return '${dias}d${horas > 0 ? ' ${horas}h' : ''}';
    if (horas > 0) return '${horas}h${minutos > 0 ? ' ${minutos}min' : ''}';
    return '${minutos > 0 ? minutos : 1} min';
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF04131F),
      appBar: AppBar(
        backgroundColor: const Color(0xFF04131F),
        leading: _concluido || _fase > 0 || _index > 0
            ? IconButton(
                icon: const Icon(Icons.arrow_back_ios_new, size: 20),
                onPressed: _voltar,
                tooltip: 'Voltar',
              )
            : null,
        title: _concluido
            ? const Text('Revisar e enviar')
            : Text(
                _fase == 0 ? 'Como você está se sentindo?' : 'Contexto clínico',
                style: const TextStyle(fontSize: 16),
              ),
        actions: [
          if (_totalSintomas > 0 && !_concluido)
            TextButton(
              onPressed: _limparTudo,
              style: TextButton.styleFrom(foregroundColor: Colors.white54),
              child: const Text('Recomeçar'),
            ),
          IconButton(
            tooltip: 'Fontes e referências',
            icon: const Icon(Icons.menu_book_outlined),
            onPressed: () => Navigator.of(context).push(
              MaterialPageRoute(builder: (_) => const TelaFontes()),
            ),
          ),
        ],
      ),
      body: _concluido ? _buildRevisao() : _buildFluxo(),
    );
  }

  // ── Fluxo de perguntas ────────────────────────────────────────────────────
  Widget _buildFluxo() {
    return Column(
      children: [
        // ── Barra de progresso ──
        _BarraProgresso(
          atual: _progressoAtual,
          total: _progressoTotal,
          fase: _fase,
        ),

        // ── Pergunta atual ──
        Expanded(
          child: AnimatedSwitcher(
            duration: const Duration(milliseconds: 220),
            transitionBuilder: (child, animation) => FadeTransition(
              opacity: animation,
              child: SlideTransition(
                position: Tween<Offset>(
                  begin: const Offset(0.04, 0),
                  end: Offset.zero,
                ).animate(CurvedAnimation(
                  parent: animation,
                  curve: Curves.easeOut,
                )),
                child: child,
              ),
            ),
            child: _fase == 0
                ? _buildCardSintoma(
                    key: ValueKey('s${_index}_$_followupAtivo'),
                  )
                : _buildCardAnamnese(
                    key: ValueKey('a$_index'),
                  ),
          ),
        ),

        // ── Rodapé: pular ──
        if (!_concluido)
          Padding(
            padding: EdgeInsets.fromLTRB(
              24,
              0,
              24,
              12 + MediaQuery.of(context).padding.bottom,
            ),
            child: TextButton(
              onPressed: () {
                if (_followupAtivo != null) {
                  setState(() => _followupAtivo = null);
                }
                _avancar();
              },
              style: TextButton.styleFrom(
                foregroundColor: Colors.white30,
              ),
              child: Text(
                _fase == 0 ? 'Não tenho certeza — pular' : 'Pular esta pergunta',
                style: const TextStyle(fontSize: 13),
              ),
            ),
          ),
      ],
    );
  }

  // ── Card de pergunta de sintoma ──
  Widget _buildCardSintoma({Key? key}) {
    final pergunta = _perguntas[_index];
    final cor = pergunta.isUrgencia
        ? const Color(0xFFFF6B6B)
        : const Color(0xFF39D0C3);
    final selecionado = _sintomas[pergunta.key] ?? false;

    return SingleChildScrollView(
      key: key,
      padding: const EdgeInsets.fromLTRB(24, 16, 24, 0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          const SizedBox(height: 12),

          // Emoji
          if (pergunta.emoji.isNotEmpty)
            Text(pergunta.emoji, style: const TextStyle(fontSize: 56)),

          const SizedBox(height: 20),

          // Pergunta
          Text(
            pergunta.pergunta,
            textAlign: TextAlign.center,
            style: TextStyle(
              color: pergunta.isUrgencia
                  ? const Color(0xFFFF6B6B)
                  : Colors.white,
              fontSize: 22,
              fontWeight: FontWeight.w800,
              height: 1.3,
            ),
          ),

          const SizedBox(height: 10),

          // Dica
          Text(
            pergunta.dica,
            textAlign: TextAlign.center,
            style: const TextStyle(
              color: Color(0xFF6A9AB5),
              fontSize: 14,
              height: 1.4,
            ),
          ),

          const SizedBox(height: 32),

          // Followup de intensidade (aparece inline após responder Sim)
          if (_followupAtivo != null)
            _buildFollowupIntensidade(_followupAtivo!)
          else ...[
            // Botões SIM / NÃO
            Row(
              children: [
                Expanded(
                  child: _BotaoGrande(
                    texto: 'Sim',
                    icone: Icons.check,
                    selecionado: selecionado,
                    cor: cor,
                    onTap: () => _responderSintoma(true),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: _BotaoGrande(
                    texto: 'Não',
                    icone: Icons.close,
                    selecionado: !selecionado && _index > 0,
                    cor: const Color(0xFF3D6680),
                    onTap: () => _responderSintoma(false),
                  ),
                ),
              ],
            ),
          ],

          const SizedBox(height: 8),
        ],
      ),
    );
  }

  // ── Follow-up de intensidade inline ──
  Widget _buildFollowupIntensidade(String tipo) {
    final isFebre = tipo == 'febre';
    final titulo = isFebre ? 'Qual a intensidade da febre?' : 'Qual a intensidade da dor articular?';
    final opcoes = isFebre
        ? [
            ('baixa', 'Baixa', 'Abaixo de 38,5°C'),
            ('moderada', 'Moderada', '38,5 – 39,5°C'),
            ('alta', 'Alta', 'Acima de 39,5°C'),
          ]
        : [
            ('leve', 'Leve', 'Não atrapalha atividades'),
            ('moderada', 'Moderada', 'Dificulta atividades'),
            ('intensa', 'Intensa', 'Incapacitante — não consegue andar'),
          ];

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(
          titulo,
          style: const TextStyle(
            color: Colors.white,
            fontSize: 17,
            fontWeight: FontWeight.w700,
          ),
        ),
        const SizedBox(height: 14),
        for (final (valor, label, detalhe) in opcoes) ...[
          _OpcaoIntensidade(
            label: label,
            detalhe: detalhe,
            onTap: () => _selecionarIntensidade(tipo, valor),
          ),
          const SizedBox(height: 8),
        ],
      ],
    );
  }

  // ── Card de pergunta de anamnese ──
  Widget _buildCardAnamnese({Key? key}) {
    final item = _anamneseItems[_index];
    final valorAtual = _valorAnamnese(_index);

    return SingleChildScrollView(
      key: key,
      padding: const EdgeInsets.fromLTRB(24, 16, 24, 0),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          const SizedBox(height: 12),

          if (item.emoji.isNotEmpty)
            Text(item.emoji, style: const TextStyle(fontSize: 52)),

          const SizedBox(height: 20),

          Text(
            item.pergunta,
            textAlign: TextAlign.center,
            style: const TextStyle(
              color: Colors.white,
              fontSize: 22,
              fontWeight: FontWeight.w800,
              height: 1.3,
            ),
          ),

          const SizedBox(height: 10),

          Text(
            item.dica,
            textAlign: TextAlign.center,
            style: const TextStyle(
              color: Color(0xFF6A9AB5),
              fontSize: 14,
              height: 1.4,
            ),
          ),

          const SizedBox(height: 32),

          // Dias de sintomas → opções de botão
          if (item.tipo == _TipoAnamnese.dias)
            _buildOpcoesDias(valorAtual as int?)
          else ...[
            Row(
              children: [
                Expanded(
                  child: _BotaoGrande(
                    texto: 'Sim',
                    icone: Icons.check,
                    selecionado: valorAtual == true,
                    cor: const Color(0xFF39D0C3),
                    onTap: () => _responderAnamnese(true),
                  ),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: _BotaoGrande(
                    texto: 'Não',
                    icone: Icons.close,
                    selecionado: valorAtual == false,
                    cor: const Color(0xFF3D6680),
                    onTap: () => _responderAnamnese(false),
                  ),
                ),
              ],
            ),
          ],

          const SizedBox(height: 8),
        ],
      ),
    );
  }

  // ── Seletor de dias ──
  Widget _buildOpcoesDias(int? valorAtual) {
    const opcoes = [
      (1, 'Hoje'),
      (2, '2–3 dias'),
      (4, '4–5 dias'),
      (7, '1 semana'),
      (14, 'Mais de 1 sem.'),
    ];
    return Wrap(
      spacing: 10,
      runSpacing: 10,
      alignment: WrapAlignment.center,
      children: [
        for (final (val, label) in opcoes)
          GestureDetector(
            onTap: () => _responderAnamnese(val),
            child: AnimatedContainer(
              duration: const Duration(milliseconds: 150),
              padding:
                  const EdgeInsets.symmetric(horizontal: 18, vertical: 12),
              decoration: BoxDecoration(
                color: valorAtual == val
                    ? const Color(0xFF39D0C3).withValues(alpha: 0.2)
                    : const Color(0xFF0B2333),
                borderRadius: BorderRadius.circular(12),
                border: Border.all(
                  color: valorAtual == val
                      ? const Color(0xFF39D0C3)
                      : const Color(0xFF1A3A50),
                  width: 1.5,
                ),
              ),
              child: Text(
                label,
                style: TextStyle(
                  color: valorAtual == val
                      ? const Color(0xFF39D0C3)
                      : Colors.white70,
                  fontWeight: valorAtual == val
                      ? FontWeight.w700
                      : FontWeight.normal,
                  fontSize: 14,
                ),
              ),
            ),
          ),
      ],
    );
  }

  // ── Tela de revisão + envio ────────────────────────────────────────────────
  Widget _buildRevisao() {
    final sintomasAtivos = _perguntas
        .where((p) => _sintomas[p.key] == true)
        .map((p) => p.emoji.isNotEmpty
            ? '${p.emoji} ${p.pergunta}'
            : p.pergunta)
        .toList();

    return ListView(
      padding: EdgeInsets.fromLTRB(
        20,
        20,
        20,
        20 + MediaQuery.of(context).padding.bottom,
      ),
      children: [
        // Cabeçalho
        Container(
          padding: const EdgeInsets.all(18),
          decoration: BoxDecoration(
            gradient: const LinearGradient(
              colors: [Color(0xFF12324B), Color(0xFF0A1B29)],
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
            ),
            borderRadius: BorderRadius.circular(20),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text(
                'Pronto para enviar',
                style: TextStyle(
                  color: Colors.white,
                  fontSize: 20,
                  fontWeight: FontWeight.w800,
                ),
              ),
              const SizedBox(height: 6),
              Text(
                '${sintomasAtivos.length} sintoma${sintomasAtivos.length != 1 ? 's' : ''} registrado${sintomasAtivos.length != 1 ? 's' : ''}. Envio anônimo e voluntário.',
                style: const TextStyle(
                  color: Color(0xFF9FC5D9),
                  fontSize: 14,
                  height: 1.4,
                ),
              ),
            ],
          ),
        ),

        const SizedBox(height: 16),

        // Sintomas marcados
        if (sintomasAtivos.isNotEmpty) ...[
          const Text(
            'Sintomas informados',
            style: TextStyle(
              color: Color(0xFF6A9AB5),
              fontSize: 13,
              fontWeight: FontWeight.w600,
            ),
          ),
          const SizedBox(height: 8),
          Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: const Color(0xFF0B2333),
              borderRadius: BorderRadius.circular(14),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                for (final s in sintomasAtivos)
                  Padding(
                    padding: const EdgeInsets.only(bottom: 6),
                    child: Text(
                      s,
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 14,
                        height: 1.4,
                      ),
                    ),
                  ),
                if (_intensidadeFebre != null)
                  Text(
                    '  Febre: intensidade $_intensidadeFebre',
                    style: const TextStyle(
                        color: Color(0xFF9FC5D9), fontSize: 13),
                  ),
                if (_intensidadeArticular != null)
                  Text(
                    '  Articular: intensidade $_intensidadeArticular',
                    style: const TextStyle(
                        color: Color(0xFF9FC5D9), fontSize: 13),
                  ),
              ],
            ),
          ),
          const SizedBox(height: 16),
        ],

        // Contexto respondido
        if (_diasSintomas != null ||
            _inicioAbrupto != null ||
            _viagemAreaEndemica != null ||
            _exposicaoAguaEnchente != null ||
            _contatoRoedores != null ||
            _contatoConfirmado != null ||
            _vacinadoFebreAmarela != null ||
            _temDiabetes != null ||
            _temHipertensao != null ||
            _temDoencaPulmonar != null ||
            _temImunossupressao != null) ...[
          const Text(
            'Contexto clínico',
            style: TextStyle(
              color: Color(0xFF6A9AB5),
              fontSize: 13,
              fontWeight: FontWeight.w600,
            ),
          ),
          const SizedBox(height: 8),
          Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: const Color(0xFF0B2333),
              borderRadius: BorderRadius.circular(14),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                if (_diasSintomas != null)
                  _InfoRow('Duração', '$_diasSintomas dia(s)'),
                if (_inicioAbrupto != null)
                  _InfoRow('Início',
                      _inicioAbrupto! ? 'Repentino' : 'Gradual'),
                if (_viagemAreaEndemica != null)
                  _InfoRow('Viagem endêmica',
                      _viagemAreaEndemica! ? 'Sim' : 'Não'),
                if (_exposicaoAguaEnchente != null)
                  _InfoRow('Água/enchente',
                      _exposicaoAguaEnchente! ? 'Sim' : 'Não'),
                if (_contatoRoedores != null)
                  _InfoRow(
                      'Contato roedores', _contatoRoedores! ? 'Sim' : 'Não'),
                if (_contatoConfirmado != null)
                  _InfoRow('Contato doente confirmado',
                      _contatoConfirmado! ? 'Sim' : 'Não'),
                if (_vacinadoFebreAmarela != null)
                  _InfoRow('Vacina Febre Amarela',
                      _vacinadoFebreAmarela! ? 'Sim' : 'Não'),
                if (_temDiabetes != null)
                  _InfoRow('Diabetes', _temDiabetes! ? 'Sim' : 'Não'),
                if (_temHipertensao != null)
                  _InfoRow('Hipertensão', _temHipertensao! ? 'Sim' : 'Não'),
                if (_temDoencaPulmonar != null)
                  _InfoRow('D. pulmonar/asma', _temDoencaPulmonar! ? 'Sim' : 'Não'),
                if (_temImunossupressao != null)
                  _InfoRow('Imunossupressão', _temImunossupressao! ? 'Sim' : 'Não'),
              ],
            ),
          ),
          const SizedBox(height: 16),
        ],

        // Resultado anterior
        if (_lastResult != null) ...[
          _FeedbackCard(data: _lastResult!),
          const SizedBox(height: 16),
        ],

        // Aviso legal
        const Text(
          'Este app não substitui atendimento médico. Em caso de agravamento, procure atendimento profissional imediatamente.',
          style: TextStyle(
              color: Color(0xFF88AFC5), height: 1.45, fontSize: 13),
        ),
        const SizedBox(height: 24),

        // Aviso de cooldown ativo
        if (_cooldown != null) ...[
          const SizedBox(height: 4),
          Container(
            width: double.infinity,
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
            decoration: BoxDecoration(
              color: const Color(0xFF0D2233),
              borderRadius: BorderRadius.circular(10),
              border: Border.all(color: const Color(0xFF1A4A6A)),
            ),
            child: Row(
              children: [
                const Icon(Icons.check_circle_outline,
                    color: Color(0xFF39D0C3), size: 20),
                const SizedBox(width: 10),
                Expanded(
                  child: Text(
                    'Você já contribuiu esta semana. Próximo envio liberado em ${_formatarCooldown(_cooldown!)}.',
                    style: const TextStyle(
                        color: Color(0xFF88AFC5), fontSize: 13, height: 1.4),
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 8),
        ],

        // Botão enviar
        FilledButton.icon(
          onPressed: _loading || _totalSintomas == 0 || _cooldown != null
              ? null
              : _enviar,
          icon: _loading
              ? const SizedBox(
                  width: 18,
                  height: 18,
                  child: CircularProgressIndicator(
                      strokeWidth: 2, color: Colors.black),
                )
              : const Icon(Icons.cloud_upload_outlined),
          label: Text(
            _loading
                ? 'Enviando...'
                : _cooldown != null
                    ? 'Envio bloqueado por 7 dias'
                    : _totalSintomas == 0
                        ? 'Nenhum sintoma selecionado'
                        : 'Enviar $_totalSintomas sintoma${_totalSintomas > 1 ? 's' : ''} agora',
          ),
          style: FilledButton.styleFrom(
            minimumSize: const Size.fromHeight(54),
            backgroundColor: _totalSintomas > 0 && _cooldown == null
                ? const Color(0xFF39D0C3)
                : const Color(0xFF1A3A50),
            foregroundColor: _totalSintomas > 0 && _cooldown == null
                ? Colors.black
                : Colors.white38,
          ),
        ),
      ],
    );
  }
}

// ─── Barra de progresso ───────────────────────────────────────────────────────
class _BarraProgresso extends StatelessWidget {
  const _BarraProgresso({
    required this.atual,
    required this.total,
    required this.fase,
  });
  final int atual;
  final int total;
  final int fase;

  @override
  Widget build(BuildContext context) {
    final progresso = total > 0 ? atual / total : 0.0;
    return Column(
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(20, 4, 20, 0),
          child: Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              Text(
                fase == 0 ? 'Sintomas' : 'Contexto clínico',
                style: const TextStyle(
                    color: Color(0xFF6A9AB5),
                    fontSize: 12,
                    fontWeight: FontWeight.w600),
              ),
              Text(
                '${atual + 1} de $total',
                style: const TextStyle(
                    color: Color(0xFF4A7A8F), fontSize: 12),
              ),
            ],
          ),
        ),
        const SizedBox(height: 6),
        LinearProgressIndicator(
          value: progresso,
          backgroundColor: const Color(0xFF0B2333),
          color: fase == 0
              ? const Color(0xFF39D0C3)
              : const Color(0xFF9B59B6),
          minHeight: 3,
        ),
        const SizedBox(height: 8),
      ],
    );
  }
}

// ─── Botão grande Sim/Não ─────────────────────────────────────────────────────
class _BotaoGrande extends StatelessWidget {
  const _BotaoGrande({
    required this.texto,
    required this.icone,
    required this.selecionado,
    required this.cor,
    required this.onTap,
  });
  final String texto;
  final IconData icone;
  final bool selecionado;
  final Color cor;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 150),
        height: 64,
        decoration: BoxDecoration(
          color: selecionado
              ? cor.withValues(alpha: 0.2)
              : const Color(0xFF0B2333),
          borderRadius: BorderRadius.circular(16),
          border: Border.all(
            color: selecionado ? cor : const Color(0xFF1A3A50),
            width: 2,
          ),
        ),
        child: Row(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(icone,
                color: selecionado ? cor : Colors.white38, size: 20),
            const SizedBox(width: 8),
            Text(
              texto,
              style: TextStyle(
                color: selecionado ? cor : Colors.white54,
                fontWeight:
                    selecionado ? FontWeight.w800 : FontWeight.w500,
                fontSize: 16,
              ),
            ),
          ],
        ),
      ),
    );
  }
}

// ─── Opção de intensidade ─────────────────────────────────────────────────────
class _OpcaoIntensidade extends StatelessWidget {
  const _OpcaoIntensidade({
    required this.label,
    required this.detalhe,
    required this.onTap,
  });
  final String label;
  final String detalhe;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        width: double.infinity,
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
        decoration: BoxDecoration(
          color: const Color(0xFF0B2333),
          borderRadius: BorderRadius.circular(14),
          border: Border.all(color: const Color(0xFF1A3A50), width: 1.5),
        ),
        child: Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    label,
                    style: const TextStyle(
                        color: Colors.white,
                        fontWeight: FontWeight.w700,
                        fontSize: 15),
                  ),
                  Text(
                    detalhe,
                    style: const TextStyle(
                        color: Color(0xFF6A9AB5), fontSize: 13),
                  ),
                ],
              ),
            ),
            const Icon(Icons.chevron_right,
                color: Color(0xFF3D6680), size: 20),
          ],
        ),
      ),
    );
  }
}

// ─── Card de feedback do último envio ────────────────────────────────────────
class _FeedbackCard extends StatelessWidget {
  const _FeedbackCard({required this.data});
  final Map<String, dynamic> data;

  @override
  Widget build(BuildContext context) {
    final local = data['local'] as Map<String, dynamic>? ?? {};
    final jaConsiderado = data['status'] == 'ja_considerado';

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(18),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'Leitura do envio',
              style: TextStyle(
                color: Colors.white,
                fontSize: 16,
                fontWeight: FontWeight.w700,
              ),
            ),
            const SizedBox(height: 10),
            _InfoRow('Sinal monitorado',
                data['grupo']?.toString() ?? 'Monitoramento geral'),
            _InfoRow('Classificação',
                data['classificacao']?.toString() ?? 'Regional'),
            _InfoRow('Qualidade do sinal', _qualidade(data)),
            _InfoRow(
              'Local identificado',
              '${local['bairro'] ?? '—'} / ${local['cidade'] ?? '—'} / ${local['estado'] ?? '—'}',
            ),
            if (jaConsiderado) ...[
              const SizedBox(height: 8),
              const Text(
                'Este envio não abriu novo caso — o radar já recebeu sinal recente deste aparelho.',
                style: TextStyle(
                    color: Color(0xFFFFD166), height: 1.35, fontSize: 13),
              ),
            ],
          ],
        ),
      ),
    );
  }

  String _qualidade(Map<String, dynamic> data) {
    final valor = (data['confianca'] as num?)?.toDouble() ?? 0;
    if (valor >= 0.85) return 'alta';
    if (valor >= 0.6) return 'moderada';
    return 'em verificação';
  }
}

// ─── InfoRow helper ───────────────────────────────────────────────────────────
class _InfoRow extends StatelessWidget {
  const _InfoRow(this.label, this.value);
  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 4),
      child: RichText(
        text: TextSpan(
          style: const TextStyle(fontSize: 13, height: 1.4),
          children: [
            TextSpan(
              text: '$label: ',
              style: const TextStyle(color: Color(0xFF6A9AB5)),
            ),
            TextSpan(
              text: value,
              style: const TextStyle(color: Color(0xFF9FC5D9)),
            ),
          ],
        ),
      ),
    );
  }
}
