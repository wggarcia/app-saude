import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../../servicos/legal_consent_service.dart';

class LegalGate extends StatefulWidget {
  const LegalGate({super.key, required this.child});

  final Widget child;

  @override
  State<LegalGate> createState() => _LegalGateState();
}

class _LegalGateState extends State<LegalGate> {
  late final Future<bool> _accepted =
      LegalConsentService.hasAcceptedCurrentTerms();
  bool _acceptedNow = false;

  @override
  Widget build(BuildContext context) {
    return FutureBuilder<bool>(
      future: _accepted,
      builder: (context, snapshot) {
        if (!snapshot.hasData) {
          return const Scaffold(
            body: Center(child: CircularProgressIndicator()),
          );
        }

        if (snapshot.data == true || _acceptedNow) {
          return widget.child;
        }

        return TelaAceiteLegal(
          onAccepted: () async {
            await LegalConsentService.acceptCurrentTerms();
            if (!mounted) {
              return;
            }
            setState(() => _acceptedNow = true);
          },
        );
      },
    );
  }
}

class TelaAceiteLegal extends StatefulWidget {
  const TelaAceiteLegal({super.key, required this.onAccepted});

  final Future<void> Function() onAccepted;

  @override
  State<TelaAceiteLegal> createState() => _TelaAceiteLegalState();
}

class _TelaAceiteLegalState extends State<TelaAceiteLegal> {
  bool _terms = false;
  bool _privacy = false;
  bool _health = false;
  bool _saving = false;

  bool get _canContinue => _terms && _privacy && _health && !_saving;

  Future<void> _accept() async {
    if (!_canContinue) {
      return;
    }

    setState(() => _saving = true);
    await widget.onAccepted();
  }

  Future<void> _decline() async {
    final sair = await showDialog<bool>(
          context: context,
          builder: (context) => AlertDialog(
            title: const Text('Aceite necessario'),
            content: const Text(
              'Para proteger voce e a integridade do radar epidemiologico, o app so pode funcionar apos a aceitacao dos Termos de Uso e da Politica de Privacidade.',
            ),
            actions: [
              TextButton(
                onPressed: () => Navigator.pop(context, false),
                child: const Text('Voltar'),
              ),
              FilledButton.tonal(
                onPressed: () => Navigator.pop(context, true),
                child: const Text('Sair do app'),
              ),
            ],
          ),
        ) ??
        false;

    if (sair) {
      SystemNavigator.pop();
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: LayoutBuilder(
          builder: (context, constraints) {
            final wide = constraints.maxWidth > 760;
            return Center(
              child: ConstrainedBox(
                constraints: BoxConstraints(maxWidth: wide ? 920 : 620),
                child: ListView(
                  padding: EdgeInsets.symmetric(
                    horizontal: wide ? 40 : 22,
                    vertical: 24,
                  ),
                  children: [
                    const _LegalHero(),
                    const SizedBox(height: 18),
                    const _LegalSection(
                      icon: Icons.verified_user_outlined,
                      title: 'Termos de Uso',
                      summary:
                          'O SolusCRT Saude e uma plataforma de monitoramento epidemiologico populacional. O app permite envio voluntario e anonimo de sinais de saude para apoiar leitura territorial de risco.',
                      items: [
                        'Use o app de boa-fe, com informacoes verdadeiras e sem tentar manipular focos, volumes ou localidades.',
                        'O app nao substitui consulta medica, diagnostico, prescricao, emergencia, SAMU, pronto atendimento ou orientacao de profissional de saude.',
                        'Alertas exibidos no app possuem finalidade informativa e preventiva, podendo variar conforme disponibilidade de dados, fontes oficiais e sinais colaborativos.',
                        'E proibido usar automacao, envio massivo, dados falsos, engenharia reversa, tentativa de invasao ou qualquer ato que comprometa o sistema.',
                      ],
                    ),
                    const _LegalSection(
                      icon: Icons.privacy_tip_outlined,
                      title: 'Politica de Privacidade e LGPD',
                      summary:
                          'Tratamos dados com finalidade de vigilancia epidemiologica, seguranca, prevencao a fraude, melhoria do radar e comunicacao de alertas publicos.',
                      items: [
                        'O app pode tratar sintomas informados, localizacao aproximada ou precisa, cidade, bairro, estado, data, identificadores tecnicos do aparelho e dados de seguranca.',
                        'Sinais de saude sao usados preferencialmente de forma agregada, estatistica e territorial, reduzindo exposicao individual.',
                        'A localizacao e usada para registrar sinais no municipio correto, mostrar focos proximos e reduzir risco de informacao falsa.',
                        'Voce pode revogar permissoes no iPhone a qualquer momento. Sem localizacao atual, algumas funcoes podem ser limitadas para proteger a confiabilidade do mapa.',
                      ],
                    ),
                    const _LegalSection(
                      icon: Icons.health_and_safety_outlined,
                      title: 'Consentimento de Saude e Localizacao',
                      summary:
                          'Dados de saude e localizacao sao sensiveis. Ao continuar, voce autoriza o tratamento necessario para o funcionamento do radar epidemiologico.',
                      items: [
                        'O envio de sintomas e voluntario e deve representar a sua situacao real no momento do envio.',
                        'O SolusCRT pode aplicar filtros antifraude por aparelho, rede, repeticao, qualidade de GPS e padroes de uso.',
                        'Casos suspeitos exibidos no mapa nao significam diagnostico confirmado; dados oficiais e sinais colaborativos sao camadas diferentes.',
                        'Em caso de falta de ar intensa, dor forte, confusao, agravamento ou emergencia, procure atendimento medico imediatamente.',
                      ],
                    ),
                    const _LegalSection(
                      icon: Icons.gavel_outlined,
                      title: 'Responsabilidade e Seguranca',
                      summary:
                          'A plataforma busca apoiar decisao responsavel, mas depende de conectividade, permissoes, disponibilidade de fontes, qualidade dos envios e validacoes tecnicas.',
                      items: [
                        'Podemos atualizar controles, regras antifraude, formas de exibicao, termos e politicas para melhorar seguranca e conformidade.',
                        'Autoridades, empresas e parceiros institucionais podem visualizar dados agregados conforme perfil contratado, permissao e finalidade adequada.',
                        'Incidentes, abuso, fraude ou risco de seguranca podem gerar bloqueio, auditoria, descarte de sinais e comunicacoes cabiveis.',
                        'Versao dos termos: ${LegalConsentService.currentVersion}.',
                      ],
                    ),
                    const SizedBox(height: 8),
                    _ConsentCheckbox(
                      value: _terms,
                      onChanged: (value) => setState(() => _terms = value),
                      text: 'Li e aceito os Termos de Uso do SolusCRT Saude.',
                    ),
                    _ConsentCheckbox(
                      value: _privacy,
                      onChanged: (value) => setState(() => _privacy = value),
                      text:
                          'Li e aceito a Politica de Privacidade e o tratamento de dados conforme a LGPD.',
                    ),
                    _ConsentCheckbox(
                      value: _health,
                      onChanged: (value) => setState(() => _health = value),
                      text:
                          'Entendo que o app nao substitui atendimento medico e autorizo o uso de localizacao e sinais de saude para o radar epidemiologico.',
                    ),
                    const SizedBox(height: 20),
                    Row(
                      children: [
                        Expanded(
                          child: OutlinedButton(
                            onPressed: _saving ? null : _decline,
                            child: const Text('Nao aceito'),
                          ),
                        ),
                        const SizedBox(width: 12),
                        Expanded(
                          flex: 2,
                          child: FilledButton(
                            onPressed: _canContinue ? _accept : null,
                            child: _saving
                                ? const SizedBox(
                                    height: 18,
                                    width: 18,
                                    child: CircularProgressIndicator(
                                      strokeWidth: 2,
                                    ),
                                  )
                                : const Text('Aceitar e continuar'),
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 20),
                  ],
                ),
              ),
            );
          },
        ),
      ),
    );
  }
}

class _LegalHero extends StatelessWidget {
  const _LegalHero();

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(28),
        gradient: const LinearGradient(
          colors: [Color(0xFF082235), Color(0xFF0B3C45)],
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
        ),
        border: Border.all(color: Colors.white12),
      ),
      child: const Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(Icons.shield_outlined, size: 42, color: Color(0xFF39D0C3)),
          SizedBox(height: 18),
          Text(
            'Antes de continuar',
            style: TextStyle(
              color: Colors.white,
              fontSize: 32,
              fontWeight: FontWeight.w900,
              letterSpacing: -0.8,
            ),
          ),
          SizedBox(height: 10),
          Text(
            'Leia e aceite os termos para usar o SolusCRT Saude com seguranca, transparencia e responsabilidade.',
            style: TextStyle(
              color: Color(0xFFC1D6E2),
              fontSize: 16,
              height: 1.45,
            ),
          ),
        ],
      ),
    );
  }
}

class _LegalSection extends StatelessWidget {
  const _LegalSection({
    required this.icon,
    required this.title,
    required this.summary,
    required this.items,
  });

  final IconData icon;
  final String title;
  final String summary;
  final List<String> items;

  @override
  Widget build(BuildContext context) {
    return Card(
      margin: const EdgeInsets.only(top: 14),
      child: Theme(
        data: Theme.of(context).copyWith(dividerColor: Colors.transparent),
        child: ExpansionTile(
          leading: Icon(icon, color: const Color(0xFF39D0C3)),
          title: Text(
            title,
            style: const TextStyle(
              color: Colors.white,
              fontWeight: FontWeight.w800,
            ),
          ),
          subtitle: Padding(
            padding: const EdgeInsets.only(top: 8),
            child: Text(
              summary,
              style: const TextStyle(color: Color(0xFF9BB8C9), height: 1.4),
            ),
          ),
          childrenPadding: const EdgeInsets.fromLTRB(20, 0, 20, 18),
          children: items
              .map(
                (item) => Padding(
                  padding: const EdgeInsets.only(top: 12),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Padding(
                        padding: EdgeInsets.only(top: 5),
                        child: Icon(
                          Icons.check_circle,
                          size: 18,
                          color: Color(0xFF39D0C3),
                        ),
                      ),
                      const SizedBox(width: 10),
                      Expanded(
                        child: Text(
                          item,
                          style: const TextStyle(
                            color: Color(0xFFD8E6EE),
                            height: 1.45,
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
              )
              .toList(),
        ),
      ),
    );
  }
}

class _ConsentCheckbox extends StatelessWidget {
  const _ConsentCheckbox({
    required this.value,
    required this.onChanged,
    required this.text,
  });

  final bool value;
  final ValueChanged<bool> onChanged;
  final String text;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: 10),
      child: InkWell(
        borderRadius: BorderRadius.circular(18),
        onTap: () => onChanged(!value),
        child: Container(
          padding: const EdgeInsets.all(16),
          decoration: BoxDecoration(
            color: const Color(0xFF071B2A),
            borderRadius: BorderRadius.circular(18),
            border: Border.all(
              color: value ? const Color(0xFF39D0C3) : Colors.white12,
            ),
          ),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Checkbox(
                value: value,
                onChanged: (next) => onChanged(next ?? false),
              ),
              const SizedBox(width: 8),
              Expanded(
                child: Padding(
                  padding: const EdgeInsets.only(top: 10),
                  child: Text(
                    text,
                    style: const TextStyle(
                      color: Colors.white,
                      height: 1.35,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
