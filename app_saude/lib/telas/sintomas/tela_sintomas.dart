import 'package:flutter/material.dart';

import '../../servicos/location_service.dart';
import '../../servicos/public_api_service.dart';
import '../../servicos/regiao_base_service.dart';

// ─── Modelo de sintoma ────────────────────────────────────────────────────────
class _Sintoma {
  const _Sintoma(this.key, this.label, this.hint);
  final String key;
  final String label;
  final String hint;
}

// ─── Grupos de sintomas ───────────────────────────────────────────────────────
class _Grupo {
  const _Grupo({
    required this.emoji,
    required this.titulo,
    required this.subtitulo,
    required this.cor,
    required this.sintomas,
  });
  final String emoji;
  final String titulo;
  final String subtitulo;
  final Color cor;
  final List<_Sintoma> sintomas;
}

const _grupos = [
  _Grupo(
    emoji: '🦟',
    titulo: 'Arbovirose / Dengue',
    subtitulo: 'Dengue, Zika, Chikungunya, Febre Amarela',
    cor: Color(0xFFFF9F43),
    sintomas: [
      _Sintoma(
          'febre', 'Febre', 'Temperatura elevada — principal sinal de dengue'),
      _Sintoma('calafrios', 'Calafrios',
          'Frio intenso mesmo com febre — malaria, dengue'),
      _Sintoma('dor_cabeca', 'Dor de cabeca',
          'Cefaleia intensa — presente em 90% das arboviroses'),
      _Sintoma('dor_corpo', 'Dor no corpo',
          'Mialgia generalizada — dengue, chikungunya'),
      _Sintoma('dor_articular', 'Dor nas articulacoes',
          'Artralgia intensa — chikungunya, zika, dengue'),
      _Sintoma('exantema', 'Manchas na pele',
          'Rash / exantema — dengue, zika, chikungunya, sarampo'),
      _Sintoma('conjuntivite', 'Olhos vermelhos',
          'Hiperemia ocular — patognomonico de Zika'),
      _Sintoma('vomito_nausea', 'Vomito ou nausea',
          'Sinal de alerta em dengue — procure atendimento'),
      _Sintoma('dor_abdominal', 'Dor abdominal',
          'Sinal de alarme — dengue grave, leptospirose'),
    ],
  ),
  _Grupo(
    emoji: '🫁',
    titulo: 'Respiratorio',
    subtitulo: 'Gripe, COVID-19, RSV, Resfriado',
    cor: Color(0xFF54A0FF),
    sintomas: [
      _Sintoma(
          'tosse', 'Tosse', 'Sinal respiratorio — gripe, COVID, resfriado'),
      _Sintoma('falta_ar', 'Falta de ar',
          'Dispneia — gripe grave, COVID, pneumonia'),
      _Sintoma('dor_garganta', 'Dor de garganta',
          'Faringite — gripe, COVID, estreptococo'),
      _Sintoma('coriza', 'Coriza / nariz escorrendo', 'Resfriado, gripe, RSV'),
      _Sintoma('perda_olfato_paladar', 'Perda de olfato ou paladar',
          'Quase patognomonico de COVID-19'),
    ],
  ),
  _Grupo(
    emoji: '🤒',
    titulo: 'Geral',
    subtitulo: 'Sintomas inespecificos e gastrointestinais',
    cor: Color(0xFF1DD1A1),
    sintomas: [
      _Sintoma('cansaco', 'Cansaco intenso',
          'Fadiga — presente em diversas infeccoes'),
      _Sintoma(
          'diarreia', 'Diarreia', 'Gastroenterite, rotavirus, dengue grave'),
      _Sintoma('ictericia', 'Pele ou olhos amarelos',
          'Ictericia — febre amarela, leptospirose, hepatite'),
    ],
  ),
  _Grupo(
    emoji: '🚨',
    titulo: 'Sinais de Urgencia',
    subtitulo: 'Procure atendimento medico imediatamente',
    cor: Color(0xFFFF6B6B),
    sintomas: [
      _Sintoma('rigidez_nuca', 'Rigidez na nuca',
          'MENINGITE — emergencia — ligue 192 ou va ao pronto-socorro'),
      _Sintoma('manchas_hemorragicas', 'Manchas roxas / sangramento',
          'Petequias — dengue hemorragico, meningite — urgencia'),
    ],
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
  final Map<String, bool> _sintomas = {};
  String? _intensidadeFebre;
  String? _intensidadeArticular;
  bool _loading = false;
  Map<String, dynamic>? _lastResult;

  int get _totalSelecionados => _sintomas.values.where((v) => v).length;

  @override
  void initState() {
    super.initState();
    for (final g in _grupos) {
      for (final s in g.sintomas) {
        _sintomas[s.key] = false;
      }
    }
  }

  void _limparTudo() {
    setState(() {
      for (final key in _sintomas.keys) {
        _sintomas[key] = false;
      }
      _intensidadeFebre = null;
      _intensidadeArticular = null;
      _lastResult = null;
    });
  }

  Future<void> _enviar() async {
    if (_totalSelecionados == 0) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Selecione ao menos um sintoma.')),
      );
      return;
    }

    final temUrgencia = (_sintomas['rigidez_nuca'] ?? false) ||
        (_sintomas['manchas_hemorragicas'] ?? false);
    if (temUrgencia) {
      final continuar = await showDialog<bool>(
        context: context,
        builder: (ctx) => AlertDialog(
          title: const Text('Sinal de urgencia detectado'),
          content: const Text(
            'Voce marcou sintomas que podem indicar emergencia medica.\n\n'
            'Ligue 192 (SAMU) ou va ao pronto-socorro imediatamente.\n\n'
            'Deseja continuar com o envio para o radar epidemiologico?',
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(ctx, false),
              child: const Text('Cancelar'),
            ),
            FilledButton(
              onPressed: () => Navigator.pop(ctx, true),
              child: const Text('Continuar envio'),
            ),
          ],
        ),
      );
      if (continuar != true) return;
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

      final jaConsiderado = result['status'] == 'ja_considerado';
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(jaConsiderado
              ? 'Envio recebido. Para proteger o mapa, repeticoes recentes entram como revisao.'
              : 'Sintomas enviados com seguranca. Obrigado por contribuir.'),
          duration: const Duration(seconds: 5),
        ),
      );
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
              'GPS atual instavel. O envio foi registrado com a melhor regiao disponivel e menor peso no mapa.',
            ),
            duration: Duration(seconds: 5),
          ),
        );
      }
      return fallback;
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Registrar sintomas'),
        actions: [
          if (_totalSelecionados > 0)
            TextButton.icon(
              onPressed: _limparTudo,
              icon: const Icon(Icons.clear_all, size: 18),
              label: const Text('Limpar'),
              style: TextButton.styleFrom(foregroundColor: Colors.white70),
            ),
        ],
      ),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(16, 12, 16, 120),
        children: [
          _HeaderCard(total: _totalSelecionados),
          const SizedBox(height: 16),
          for (final grupo in _grupos) ...[
            _GrupoExpansion(
              grupo: grupo,
              sintomas: _sintomas,
              intensidadeFebre: _intensidadeFebre,
              intensidadeArticular: _intensidadeArticular,
              onSintomaChanged: (key, value) =>
                  setState(() => _sintomas[key] = value),
              onIntensidadeFebreChanged: (v) =>
                  setState(() => _intensidadeFebre = v),
              onIntensidadeArticularChanged: (v) =>
                  setState(() => _intensidadeArticular = v),
            ),
            const SizedBox(height: 10),
          ],
          if (_lastResult != null) ...[
            const SizedBox(height: 8),
            _FeedbackCard(data: _lastResult!),
            const SizedBox(height: 8),
          ],
          const Padding(
            padding: EdgeInsets.symmetric(vertical: 8),
            child: Text(
              'Este app nao substitui atendimento medico. Em caso de agravamento, '
              'procure atendimento profissional imediatamente.',
              style: TextStyle(
                  color: Color(0xFF88AFC5), height: 1.45, fontSize: 13),
            ),
          ),
        ],
      ),
      bottomNavigationBar: _BotaoEnviar(
        total: _totalSelecionados,
        loading: _loading,
        onEnviar: _enviar,
      ),
    );
  }
}

// ─── Header com contador ──────────────────────────────────────────────────────
class _HeaderCard extends StatelessWidget {
  const _HeaderCard({required this.total});
  final int total;

  @override
  Widget build(BuildContext context) {
    return Container(
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
          Row(
            children: [
              const Expanded(
                child: Text(
                  'Selecione seus sintomas',
                  style: TextStyle(
                    color: Colors.white,
                    fontSize: 20,
                    fontWeight: FontWeight.w800,
                  ),
                ),
              ),
              if (total > 0)
                Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                  decoration: BoxDecoration(
                    color: const Color(0xFF39D0C3),
                    borderRadius: BorderRadius.circular(999),
                  ),
                  child: Text(
                    '$total selecionado${total > 1 ? 's' : ''}',
                    style: const TextStyle(
                      color: Colors.black,
                      fontWeight: FontWeight.w700,
                      fontSize: 13,
                    ),
                  ),
                ),
            ],
          ),
          const SizedBox(height: 8),
          const Text(
            'Envio anonimo e voluntario. Sem cadastro nominal. '
            'Contribui para o monitoramento epidemiologico da sua regiao.',
            style:
                TextStyle(color: Color(0xFF9FC5D9), height: 1.45, fontSize: 14),
          ),
        ],
      ),
    );
  }
}

// ─── Grupo expansivel (dropdown) ──────────────────────────────────────────────
class _GrupoExpansion extends StatefulWidget {
  const _GrupoExpansion({
    required this.grupo,
    required this.sintomas,
    required this.intensidadeFebre,
    required this.intensidadeArticular,
    required this.onSintomaChanged,
    required this.onIntensidadeFebreChanged,
    required this.onIntensidadeArticularChanged,
  });

  final _Grupo grupo;
  final Map<String, bool> sintomas;
  final String? intensidadeFebre;
  final String? intensidadeArticular;
  final void Function(String key, bool value) onSintomaChanged;
  final void Function(String? v) onIntensidadeFebreChanged;
  final void Function(String? v) onIntensidadeArticularChanged;

  @override
  State<_GrupoExpansion> createState() => _GrupoExpansionState();
}

class _GrupoExpansionState extends State<_GrupoExpansion> {
  bool _expanded = false;

  int get _selecionados => widget.grupo.sintomas
      .where((s) => widget.sintomas[s.key] ?? false)
      .length;

  @override
  Widget build(BuildContext context) {
    final cor = widget.grupo.cor;
    final sel = _selecionados;

    return Container(
      decoration: BoxDecoration(
        color: const Color(0xFF0B2333),
        borderRadius: BorderRadius.circular(18),
        border: Border.all(
          color: sel > 0 ? cor.withValues(alpha: 0.5) : Colors.transparent,
          width: 1.5,
        ),
      ),
      child: Theme(
        data: Theme.of(context).copyWith(dividerColor: Colors.transparent),
        child: ExpansionTile(
          initiallyExpanded: _expanded,
          onExpansionChanged: (v) => setState(() => _expanded = v),
          tilePadding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
          childrenPadding: const EdgeInsets.fromLTRB(12, 0, 12, 12),
          leading: Container(
            width: 42,
            height: 42,
            decoration: BoxDecoration(
              color: cor.withValues(alpha: 0.15),
              borderRadius: BorderRadius.circular(12),
            ),
            child: Center(
              child: Text(widget.grupo.emoji,
                  style: const TextStyle(fontSize: 20)),
            ),
          ),
          title: Text(
            widget.grupo.titulo,
            style: const TextStyle(
              color: Colors.white,
              fontWeight: FontWeight.w700,
              fontSize: 15,
            ),
          ),
          subtitle: Row(
            children: [
              Expanded(
                child: Text(
                  widget.grupo.subtitulo,
                  style: TextStyle(
                      color: cor.withValues(alpha: 0.85), fontSize: 12),
                ),
              ),
              if (sel > 0)
                Container(
                  margin: const EdgeInsets.only(left: 8),
                  padding:
                      const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                  decoration: BoxDecoration(
                    color: cor.withValues(alpha: 0.2),
                    borderRadius: BorderRadius.circular(999),
                  ),
                  child: Text(
                    '$sel',
                    style: TextStyle(
                      color: cor,
                      fontSize: 12,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                ),
            ],
          ),
          iconColor: Colors.white54,
          collapsedIconColor: Colors.white38,
          children: [
            const Divider(color: Color(0xFF1A3A50), height: 1),
            const SizedBox(height: 8),
            for (final sintoma in widget.grupo.sintomas) ...[
              _SintomaCheckTile(
                sintoma: sintoma,
                value: widget.sintomas[sintoma.key] ?? false,
                cor: cor,
                onChanged: (v) => widget.onSintomaChanged(sintoma.key, v),
              ),
              if (sintoma.key == 'febre' && (widget.sintomas['febre'] ?? false))
                _DropdownIntensidade(
                  label: 'Intensidade da febre',
                  value: widget.intensidadeFebre,
                  opcoes: const [
                    _OpcaoDropdown('baixa', 'Baixa (abaixo de 38,5°C)'),
                    _OpcaoDropdown('moderada', 'Moderada (38,5 – 39,5°C)'),
                    _OpcaoDropdown('alta', 'Alta (acima de 39,5°C)'),
                  ],
                  onChanged: widget.onIntensidadeFebreChanged,
                ),
              if (sintoma.key == 'dor_articular' &&
                  (widget.sintomas['dor_articular'] ?? false))
                _DropdownIntensidade(
                  label: 'Intensidade da dor articular',
                  value: widget.intensidadeArticular,
                  opcoes: const [
                    _OpcaoDropdown('leve', 'Leve — nao atrapalha atividades'),
                    _OpcaoDropdown(
                        'moderada', 'Moderada — dificulta atividades'),
                    _OpcaoDropdown('intensa', 'Intensa — incapacitante'),
                  ],
                  onChanged: widget.onIntensidadeArticularChanged,
                ),
            ],
          ],
        ),
      ),
    );
  }
}

// ─── Tile de sintoma ──────────────────────────────────────────────────────────
class _SintomaCheckTile extends StatelessWidget {
  const _SintomaCheckTile({
    required this.sintoma,
    required this.value,
    required this.cor,
    required this.onChanged,
  });

  final _Sintoma sintoma;
  final bool value;
  final Color cor;
  final void Function(bool) onChanged;

  @override
  Widget build(BuildContext context) {
    return CheckboxListTile(
      dense: true,
      controlAffinity: ListTileControlAffinity.leading,
      value: value,
      activeColor: cor,
      checkColor: Colors.black,
      onChanged: (v) => onChanged(v ?? false),
      title: Text(
        sintoma.label,
        style: TextStyle(
          color: value ? Colors.white : Colors.white70,
          fontWeight: value ? FontWeight.w600 : FontWeight.normal,
          fontSize: 14,
        ),
      ),
      subtitle: Text(
        sintoma.hint,
        style: const TextStyle(color: Color(0xFF6A9AB5), fontSize: 12),
      ),
    );
  }
}

// ─── Dropdown de intensidade ──────────────────────────────────────────────────
class _OpcaoDropdown {
  const _OpcaoDropdown(this.value, this.label);
  final String value;
  final String label;
}

class _DropdownIntensidade extends StatelessWidget {
  const _DropdownIntensidade({
    required this.label,
    required this.value,
    required this.opcoes,
    required this.onChanged,
  });

  final String label;
  final String? value;
  final List<_OpcaoDropdown> opcoes;
  final void Function(String?) onChanged;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(16, 4, 16, 8),
      child: DropdownButtonFormField<String>(
        initialValue: value,
        decoration: InputDecoration(
          labelText: label,
          labelStyle: const TextStyle(color: Color(0xFF9FC5D9), fontSize: 13),
          filled: true,
          fillColor: const Color(0xFF112E43),
          border: OutlineInputBorder(
            borderRadius: BorderRadius.circular(12),
            borderSide: BorderSide.none,
          ),
          contentPadding:
              const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
        ),
        dropdownColor: const Color(0xFF0F2D42),
        style: const TextStyle(color: Colors.white, fontSize: 14),
        hint: const Text('Selecionar',
            style: TextStyle(color: Color(0xFF6A9AB5))),
        items: [
          const DropdownMenuItem<String>(
            value: null,
            child: Text('Nao informado',
                style: TextStyle(color: Color(0xFF6A9AB5))),
          ),
          for (final op in opcoes)
            DropdownMenuItem<String>(
              value: op.value,
              child: Text(op.label),
            ),
        ],
        onChanged: onChanged,
      ),
    );
  }
}

// ─── Botao enviar fixo no bottom ──────────────────────────────────────────────
class _BotaoEnviar extends StatelessWidget {
  const _BotaoEnviar({
    required this.total,
    required this.loading,
    required this.onEnviar,
  });

  final int total;
  final bool loading;
  final VoidCallback onEnviar;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: EdgeInsets.fromLTRB(
        16,
        12,
        16,
        12 + MediaQuery.of(context).padding.bottom,
      ),
      decoration: const BoxDecoration(
        color: Color(0xFF04131F),
        border: Border(top: BorderSide(color: Color(0xFF112E43))),
      ),
      child: FilledButton.icon(
        onPressed: loading ? null : onEnviar,
        icon: loading
            ? const SizedBox(
                width: 18,
                height: 18,
                child: CircularProgressIndicator(
                    strokeWidth: 2, color: Colors.black),
              )
            : const Icon(Icons.cloud_upload_outlined),
        label: Text(
          loading
              ? 'Enviando...'
              : total == 0
                  ? 'Selecione ao menos um sintoma'
                  : 'Enviar $total sintoma${total > 1 ? 's' : ''} agora',
        ),
        style: FilledButton.styleFrom(
          minimumSize: const Size.fromHeight(54),
          backgroundColor:
              total > 0 ? const Color(0xFF39D0C3) : const Color(0xFF1A3A50),
          foregroundColor: total > 0 ? Colors.black : Colors.white38,
        ),
      ),
    );
  }
}

// ─── Card de feedback ─────────────────────────────────────────────────────────
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
            _InfoRow('Classificacao',
                data['classificacao']?.toString() ?? 'Regional'),
            _InfoRow('Qualidade do sinal', _qualidade(data)),
            _InfoRow(
              'Local identificado',
              '${local['bairro'] ?? '—'} / ${local['cidade'] ?? '—'} / ${local['estado'] ?? '—'}',
            ),
            if (jaConsiderado) ...[
              const SizedBox(height: 8),
              const Text(
                'Este envio nao abriu novo caso — o radar ja recebeu sinal recente deste aparelho.',
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
    return 'em verificacao';
  }
}

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
