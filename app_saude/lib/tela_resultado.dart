import 'package:flutter/material.dart';

class TelaResultado extends StatelessWidget {
  final Map<String, dynamic> cidadao;
  final Map<String, dynamic> local;

  const TelaResultado({
    super.key,
    required this.cidadao,
    required this.local,
  });

  static const _bg        = Color(0xFF04131F);
  static const _panel     = Color(0xFF0B2333);
  static const _accent    = Color(0xFF39D0C3);
  static const _secondary = Color(0xFFFFA657);
  static const _error     = Color(0xFFFF6B6B);

  static const _corMap = {
    'verde':    _CorAlerta(header: _accent,           icon: Icons.check_circle_outline,     label: 'Acompanhamento domiciliar'),
    'amarela':  _CorAlerta(header: _secondary,        icon: Icons.warning_amber_outlined,   label: 'Atenção — monitorar'),
    'laranja':  _CorAlerta(header: Color(0xFFFF8C42), icon: Icons.medical_services_outlined, label: 'Procure uma UBS'),
    'vermelha': _CorAlerta(header: _error,            icon: Icons.emergency_outlined,       label: 'URGÊNCIA — pronto-socorro'),
    'cinza':    _CorAlerta(header: Color(0xFF4A6278), icon: Icons.help_outline,             label: 'Continuar monitorando'),
  };

  @override
  Widget build(BuildContext context) {
    final cor      = cidadao['cor_alerta']    as String?               ?? 'cinza';
    final sindrome = cidadao['sindrome']      as String?               ?? 'Sintomas em Acompanhamento';
    final conduta  = cidadao['conduta']       as String?               ?? 'Continue monitorando seus sintomas.';
    final alerta   = cidadao['alerta_urgente'] as Map<String, dynamic>?;
    final safeguard = cidadao['safeguard']    as String?;

    final visual   = _corMap[cor] ?? _corMap['cinza']!;
    final cidade   = local['cidade'] as String? ?? '';
    final estado   = local['estado'] as String? ?? '';
    final localStr = [cidade, estado].where((s) => s.isNotEmpty).join(', ');

    return Scaffold(
      backgroundColor: _bg,
      body: SafeArea(
        child: Column(
          children: [
            _Header(visual: visual, sindrome: sindrome),
            Expanded(
              child: SingleChildScrollView(
                padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 18),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    if (alerta != null) ...[
                      _UrgenciaCard(alerta: alerta),
                      const SizedBox(height: 14),
                    ],
                    _ConductaCard(conduta: conduta, accentColor: visual.header),
                    const SizedBox(height: 14),
                    _MapaCard(localStr: localStr),
                    const SizedBox(height: 14),
                    _AvisoLegal(texto: safeguard ??
                        'Avaliação automatizada de apoio. Não substitui '
                        'diagnóstico médico, exames laboratoriais ou '
                        'avaliação clínica presencial.'),
                    const SizedBox(height: 24),
                  ],
                ),
              ),
            ),
            _BotaoFechar(accentColor: visual.header, onTap: () => Navigator.of(context).pop()),
          ],
        ),
      ),
    );
  }
}

// ── Cabeçalho ─────────────────────────────────────────────────────────────
class _Header extends StatelessWidget {
  const _Header({required this.visual, required this.sindrome});
  final _CorAlerta visual;
  final String sindrome;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.fromLTRB(20, 22, 20, 26),
      decoration: BoxDecoration(
        color: TelaResultado._panel,
        border: Border(bottom: BorderSide(color: visual.header, width: 2)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(visual.icon, color: visual.header, size: 22),
              const SizedBox(width: 8),
              Text(
                visual.label,
                style: TextStyle(
                  color: visual.header,
                  fontSize: 12,
                  fontWeight: FontWeight.w600,
                  letterSpacing: 0.4,
                ),
              ),
            ],
          ),
          const SizedBox(height: 10),
          Text(
            sindrome,
            style: const TextStyle(color: Colors.white, fontSize: 22, fontWeight: FontWeight.w700, height: 1.2),
          ),
          const SizedBox(height: 5),
          Text(
            'Padrão identificado pela IA epidemiológica',
            style: TextStyle(color: Colors.white.withValues(alpha: 0.45), fontSize: 12),
          ),
        ],
      ),
    );
  }
}

// ── Urgência absoluta ─────────────────────────────────────────────────────
class _UrgenciaCard extends StatelessWidget {
  const _UrgenciaCard({required this.alerta});
  final Map<String, dynamic> alerta;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0xFF2A0F0F),
        border: Border.all(color: TelaResultado._error.withValues(alpha: 0.5)),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Icon(Icons.emergency, color: TelaResultado._error, size: 20),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  alerta['titulo'] as String? ?? 'URGÊNCIA',
                  style: const TextStyle(color: TelaResultado._error, fontWeight: FontWeight.w700, fontSize: 13),
                ),
                const SizedBox(height: 4),
                Text(
                  alerta['acao'] as String? ?? 'Dirija-se imediatamente ao pronto-socorro mais próximo.',
                  style: TextStyle(color: TelaResultado._error.withValues(alpha: 0.85), fontSize: 13, height: 1.45),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

// ── Conduta ───────────────────────────────────────────────────────────────
class _ConductaCard extends StatelessWidget {
  const _ConductaCard({required this.conduta, required this.accentColor});
  final String conduta;
  final Color accentColor;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: TelaResultado._panel,
        border: Border(left: BorderSide(color: accentColor, width: 3)),
        borderRadius: const BorderRadius.only(
          topRight: Radius.circular(10),
          bottomRight: Radius.circular(10),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            'O que fazer agora',
            style: TextStyle(fontWeight: FontWeight.w600, fontSize: 12, color: accentColor, letterSpacing: 0.3),
          ),
          const SizedBox(height: 8),
          Text(
            conduta,
            style: TextStyle(fontSize: 14, height: 1.6, color: Colors.white.withValues(alpha: 0.88)),
          ),
        ],
      ),
    );
  }
}

// ── Registro no mapa ─────────────────────────────────────────────────────
class _MapaCard extends StatelessWidget {
  const _MapaCard({required this.localStr});
  final String localStr;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 14),
      decoration: BoxDecoration(
        color: TelaResultado._panel,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: TelaResultado._accent.withValues(alpha: 0.25), width: 0.5),
      ),
      child: Row(
        children: [
          const Icon(Icons.location_on_outlined, color: TelaResultado._accent, size: 20),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text('Seu relato foi registrado',
                    style: TextStyle(fontWeight: FontWeight.w600, fontSize: 13, color: Colors.white)),
                if (localStr.isNotEmpty)
                  Text('Região: $localStr',
                      style: TextStyle(fontSize: 12, color: Colors.white.withValues(alpha: 0.5))),
                Text('Dados alimentam o mapa epidemiológico regional de forma anônima.',
                    style: TextStyle(fontSize: 12, color: Colors.white.withValues(alpha: 0.5))),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

// ── Aviso legal ───────────────────────────────────────────────────────────
class _AvisoLegal extends StatelessWidget {
  const _AvisoLegal({required this.texto});
  final String texto;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: TelaResultado._panel.withValues(alpha: 0.6),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(Icons.info_outline, size: 15, color: Colors.white.withValues(alpha: 0.3)),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              texto,
              style: TextStyle(fontSize: 11, color: Colors.white.withValues(alpha: 0.4), height: 1.5),
            ),
          ),
        ],
      ),
    );
  }
}

// ── Botão fechar ──────────────────────────────────────────────────────────
class _BotaoFechar extends StatelessWidget {
  const _BotaoFechar({required this.accentColor, required this.onTap});
  final Color accentColor;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(20, 8, 20, 20),
      child: SizedBox(
        width: double.infinity,
        height: 52,
        child: ElevatedButton(
          onPressed: onTap,
          style: ElevatedButton.styleFrom(
            backgroundColor: accentColor,
            foregroundColor: const Color(0xFF04131F),
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
            elevation: 0,
          ),
          child: const Text('Fechar', style: TextStyle(fontSize: 16, fontWeight: FontWeight.w700)),
        ),
      ),
    );
  }
}

// ── Modelo de cor ─────────────────────────────────────────────────────────
class _CorAlerta {
  const _CorAlerta({required this.header, required this.icon, required this.label});
  final Color header;
  final IconData icon;
  final String label;
}
