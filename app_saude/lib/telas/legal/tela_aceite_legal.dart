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
            title: const Text('Aceite necessário'),
            content: const Text(
              'Para proteger você e a integridade do radar de sinais de saúde, o app só pode funcionar após a aceitação dos Termos de Uso e da Política de Privacidade.',
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
                          'O SoloCRT Saúde é um aplicativo privado e gratuito da SoloCRT para acompanhamento de sinais de saúde da comunidade. O app permite envio voluntário de sinais de saúde para apoiar uma leitura territorial de tendências.',
                      items: [
                        'Use o app de boa-fé, com informações verdadeiras e sem tentar manipular focos, volumes ou localidades.',
                        'O app não substitui consulta médica, diagnóstico, prescrição, emergência, SAMU, pronto atendimento ou orientação de profissional de saúde.',
                        'Alertas exibidos no app possuem finalidade informativa e preventiva, podendo variar conforme disponibilidade de dados, fontes oficiais e sinais colaborativos.',
                        'É proibido usar automação, envio massivo, dados falsos, engenharia reversa, tentativa de invasão ou qualquer ato que comprometa o sistema.',
                      ],
                    ),
                    const _LegalSection(
                      icon: Icons.privacy_tip_outlined,
                      title: 'Política de Privacidade e LGPD',
                      summary:
                          'Tratamos dados com finalidade de inteligência epidemiológica, segurança, prevenção à fraude, melhoria do radar e comunicação de alertas.',
                      items: [
                        'O app pode tratar sintomas informados, localização aproximada ou precisa, cidade, bairro, estado, data, identificador técnico aleatório do app e dados de segurança.',
                        'Sinais de saúde são usados preferencialmente de forma agregada, estatística e territorial, reduzindo exposição individual.',
                        'A localização é usada para registrar sinais no município correto, mostrar focos próximos e reduzir risco de informação falsa.',
                        'Você pode revogar permissões no iPhone a qualquer momento. Sem localização atual, algumas funções podem ser limitadas para proteger a confiabilidade do mapa.',
                        'Conforme a LGPD (Lei 13.709/2018), você tem direito de solicitar acesso, correção ou exclusão dos seus dados a qualquer momento pelo e-mail privacidade@solocrt.com.',
                      ],
                    ),
                    const _LegalSection(
                      icon: Icons.health_and_safety_outlined,
                      title: 'Consentimento de Saúde e Localização',
                      summary:
                          'Dados de saúde e localização são sensíveis. Ao continuar, você autoriza o tratamento necessário para o funcionamento do radar de sinais de saúde.',
                      items: [
                        'O envio de sintomas é voluntário e deve representar a sua situação real no momento do envio.',
                        'O SoloCRT pode aplicar filtros antifraude por aparelho, rede, repetição, qualidade de GPS e padrões de uso.',
                        'Casos suspeitos exibidos no mapa não significam diagnóstico confirmado; dados oficiais e sinais colaborativos são camadas diferentes.',
                        'Em caso de falta de ar intensa, dor forte, confusão, agravamento ou emergência, procure atendimento médico imediatamente.',
                      ],
                    ),
                    const _LegalSection(
                      icon: Icons.gavel_outlined,
                      title: 'Responsabilidade e Segurança',
                      summary:
                          'A plataforma busca apoiar decisão responsável, mas depende de conectividade, permissões, disponibilidade de fontes, qualidade dos envios e validações técnicas.',
                      items: [
                        'Podemos atualizar controles, regras antifraude, formas de exibição, termos e políticas para melhorar segurança e conformidade.',
                        'A SoloCRT pode exibir indicadores agregados e anônimos conforme finalidade adequada, permissão e perfil contratado.',
                        'Incidentes, abuso, fraude ou risco de segurança podem gerar bloqueio, auditoria, descarte de sinais e comunicações cabíveis.',
                        'Versão dos termos: ${LegalConsentService.currentVersion}.',
                      ],
                    ),
                    const SizedBox(height: 8),
                    _ConsentCheckbox(
                      value: _terms,
                      onChanged: (value) => setState(() => _terms = value),
                      text: 'Li e aceito os Termos de Uso do SoloCRT Saúde.',
                    ),
                    _ConsentCheckbox(
                      value: _privacy,
                      onChanged: (value) => setState(() => _privacy = value),
                      text:
                          'Li e aceito a Política de Privacidade e o tratamento de dados conforme a LGPD.',
                    ),
                    _ConsentCheckbox(
                      value: _health,
                      onChanged: (value) => setState(() => _health = value),
                      text:
                          'Entendo que o app não substitui atendimento médico e autorizo o uso de localização e sinais de saúde para o funcionamento do radar.',
                    ),
                    const SizedBox(height: 20),
                    Row(
                      children: [
                        Expanded(
                          child: OutlinedButton(
                            onPressed: _saving ? null : _decline,
                            child: const Text('Não aceito'),
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
            'Leia e aceite os termos para usar o SoloCRT Saúde com segurança, transparência e responsabilidade.',
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
