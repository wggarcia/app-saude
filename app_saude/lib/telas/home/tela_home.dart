import 'package:flutter/material.dart';

import '../../servicos/alerta_inbox_service.dart';
import '../../servicos/location_service.dart';
import '../../servicos/public_api_service.dart';
import '../../servicos/push_service.dart';
import '../../servicos/regiao_base_service.dart';
import '../alertas/tela_alertas.dart';
import '../mapa/tela_mapa.dart';
import '../sintomas/tela_sintomas.dart';

class TelaHome extends StatefulWidget {
  const TelaHome({super.key});

  @override
  State<TelaHome> createState() => _TelaHomeState();
}

class _TelaHomeState extends State<TelaHome> {
  int currentIndex = 0;
  bool _locationPrimerShown = false;

  final List<Widget> _pages = const [
    TelaPainelCidadao(),
    TelaSintomas(),
    TelaMapa(),
    TelaAlertas(),
  ];

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _prepararPermissaoLocalizacao();
    });
  }

  Future<void> _prepararPermissaoLocalizacao() async {
    if (!mounted || _locationPrimerShown) {
      return;
    }
    _locationPrimerShown = true;

    final autorizado = await LocationService.solicitarPermissaoInicial();
    if (autorizado || !mounted) {
      return;
    }

    final abrirAjustes = await showDialog<bool>(
          context: context,
          builder: (context) => AlertDialog(
            title: const Text('Ativar localizacao do SolusCRT'),
            content: const Text(
              'O app precisa pedir permissao de localizacao ao iPhone para mostrar focos perto de voce e enviar sintomas no municipio correto. Toque em Permitir quando o iPhone solicitar.',
            ),
            actions: [
              TextButton(
                onPressed: () => Navigator.pop(context, false),
                child: const Text('Depois'),
              ),
              FilledButton(
                onPressed: () => Navigator.pop(context, true),
                child: const Text('Ativar agora'),
              ),
            ],
          ),
        ) ??
        false;

    if (!abrirAjustes) {
      return;
    }

    final permitido = await LocationService.solicitarPermissaoInicial();
    if (!permitido) {
      await LocationService.abrirAjustesLocalizacao();
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: _pages[currentIndex],
      bottomNavigationBar: NavigationBar(
        height: 74,
        backgroundColor: const Color(0xFF0B2333),
        selectedIndex: currentIndex,
        onDestinationSelected: (value) {
          setState(() => currentIndex = value);
        },
        destinations: const [
          NavigationDestination(
            icon: Icon(Icons.radar_outlined),
            selectedIcon: Icon(Icons.radar),
            label: 'Radar',
          ),
          NavigationDestination(
            icon: Icon(Icons.favorite_border),
            selectedIcon: Icon(Icons.favorite),
            label: 'Sintomas',
          ),
          NavigationDestination(
            icon: Icon(Icons.public_outlined),
            selectedIcon: Icon(Icons.public),
            label: 'Mapa',
          ),
          NavigationDestination(
            icon: Icon(Icons.notifications_none_outlined),
            selectedIcon: Icon(Icons.notifications),
            label: 'Alertas',
          ),
        ],
      ),
    );
  }
}

class TelaPainelCidadao extends StatefulWidget {
  const TelaPainelCidadao({super.key});

  @override
  State<TelaPainelCidadao> createState() => _TelaPainelCidadaoState();
}

class _TelaPainelCidadaoState extends State<TelaPainelCidadao> {
  Map<String, dynamic>? resumo;
  Map<String, dynamic>? radarSelecionado;
  Map<String, dynamic>? radarAtual;
  Map<String, dynamic>? regiaoBase;
  List<dynamic> alertasPublicos = const [];
  String modoMonitoramento = 'atual';
  bool loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<Map<String, dynamic>> _resolverRadarPreferido({
    required String modo,
    required Map<String, dynamic> radarAgora,
    required Map<String, dynamic>? base,
  }) async {
    if (modo == 'base' && base != null) {
      try {
        return await PublicApiService.fetchRadarLocal(
          cidade: (base['cidade'])?.toString(),
          estado: (base['estado'])?.toString(),
          bairro: (base['bairro'])?.toString(),
        );
      } catch (_) {
        return radarAgora;
      }
    }
    return radarAgora;
  }

  Future<void> _load() async {
    try {
      final modo = await RegiaoBaseService.obterModoMonitoramento();
      final base = await RegiaoBaseService.obterRegiaoBase();
      final location = await LocationService.getBestEffortLocation(
        fallbackRegion: base,
      );
      final radarAgora = await PublicApiService.fetchRadarLocal(
        latitude: location.latitude,
        longitude: location.longitude,
      );
      if (location.source == 'current') {
        await RegiaoBaseService.registrarObservacao(
          local: radarAgora['local'] as Map<String, dynamic>? ?? {},
          latitude: location.latitude,
          longitude: location.longitude,
        );
      }
      final updatedBase = await RegiaoBaseService.obterRegiaoBase();
      final radarPreferido = await _resolverRadarPreferido(
        modo: modo,
        radarAgora: radarAgora,
        base: updatedBase,
      );
      final results = await Future.wait([
        PublicApiService.fetchResumo(),
        PublicApiService.fetchAlertas(
          cidade: (radarPreferido['local'] as Map<String, dynamic>?)?['cidade']
              ?.toString(),
          estado: (radarPreferido['local'] as Map<String, dynamic>?)?['estado']
              ?.toString(),
          bairro: (radarPreferido['local'] as Map<String, dynamic>?)?['bairro']
              ?.toString(),
        ),
      ]);
      if (!mounted) {
        return;
      }
      setState(() {
        resumo = results[0] as Map<String, dynamic>;
        radarSelecionado = radarPreferido;
        radarAtual = radarAgora;
        regiaoBase = updatedBase;
        alertasPublicos = results[1] as List<dynamic>;
        modoMonitoramento = modo;
        loading = false;
      });
      final pushLocal = radarAgora['local'] as Map<String, dynamic>? ?? {};
      await PushService.syncRegion(
        estado: pushLocal['estado']?.toString(),
        cidade: pushLocal['cidade']?.toString(),
        bairro: pushLocal['bairro']?.toString(),
      );
      await _notificarNovosAlertas(results[1] as List<dynamic>);
    } catch (_) {
      try {
        final modo = await RegiaoBaseService.obterModoMonitoramento();
        final data = await PublicApiService.fetchResumo();
        final base = await RegiaoBaseService.obterRegiaoBase();
        Map<String, dynamic>? radar;
        if (base != null) {
          radar = await PublicApiService.fetchRadarLocal(
            cidade: base['cidade']?.toString(),
            estado: base['estado']?.toString(),
            bairro: base['bairro']?.toString(),
          );
        }
        if (!mounted) {
          return;
        }
        setState(() {
          resumo = data;
          radarSelecionado = radar;
          radarAtual = radar;
          regiaoBase = base;
          alertasPublicos = const [];
          modoMonitoramento = modo;
          loading = false;
        });
      } catch (_) {
        if (!mounted) {
          return;
        }
        setState(() => loading = false);
      }
    }
  }

  Future<void> _notificarNovosAlertas(List<dynamic> alertas) async {
    await AlertaInboxService.syncAlerts(alertas);
    final novos = await AlertaInboxService.captureNewAlerts(alertas);
    await _abrirAlertaSeExistir(novos, permitirLembrarDepois: true);
  }

  Future<void> _abrirAlertaSeExistir(
    List<Map<String, dynamic>> alertas, {
    required bool permitirLembrarDepois,
  }) async {
    if (!mounted || alertas.isEmpty) {
      return;
    }

    final alerta = alertas.first;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) {
        return;
      }
      showDialog<void>(
        context: context,
        builder: (context) {
          return AlertDialog(
            backgroundColor: const Color(0xFF0B2333),
            title: Text(
              alerta['titulo']?.toString() ?? 'Alerta governamental',
              style: const TextStyle(color: Colors.white),
            ),
            content: Text(
              alerta['mensagem']?.toString() ?? '',
              style: const TextStyle(color: Color(0xFFBEE9FF), height: 1.4),
            ),
            actions: [
              if (permitirLembrarDepois)
                TextButton(
                  onPressed: () async {
                    final id = (alerta['id'] as num?)?.toInt();
                    if (id != null) {
                      await AlertaInboxService.forgetAlert(id);
                    }
                    if (context.mounted) {
                      Navigator.of(context).pop();
                    }
                  },
                  child: const Text('Lembrar depois'),
                ),
              TextButton(
                onPressed: () => Navigator.of(context).pop(),
                child: const Text('Fechar'),
              ),
            ],
          );
        },
      );
    });
  }

  Future<void> _alterarModo(String modo) async {
    if (modoMonitoramento == modo) {
      return;
    }
    setState(() {
      modoMonitoramento = modo;
      loading = true;
    });
    await RegiaoBaseService.salvarModoMonitoramento(modo);
    await _load();
  }

  @override
  Widget build(BuildContext context) {
    final resumoData = resumo?['resumo'] as Map<String, dynamic>? ?? {};
    final doencas = resumo?['doencas_top'] as List<dynamic>? ?? [];
    final radar = radarSelecionado?['radar'] as Map<String, dynamic>? ?? {};
    final local = radarSelecionado?['local'] as Map<String, dynamic>? ?? {};
    final localAtual = radarAtual?['local'] as Map<String, dynamic>? ?? {};
    final estaForaDaBase = RegiaoBaseService.estaForaDaRegiaoBase(
      regiaoBase: regiaoBase,
      localAtual: localAtual,
    );
    final semaforo = radarSelecionado?['semaforo'] as Map<String, dynamic>? ??
        resumo?['semaforo'] as Map<String, dynamic>? ??
        {};
    final alertaPublico =
        radarSelecionado?['alerta_publico'] as Map<String, dynamic>? ??
            resumo?['alerta_publico'] as Map<String, dynamic>? ??
            {};
    final orientacao =
        radarSelecionado?['orientacao_publica'] as Map<String, dynamic>? ??
            resumo?['orientacao_publica'] as Map<String, dynamic>? ??
            {};

    return CustomScrollView(
      slivers: [
        SliverAppBar.large(
          pinned: true,
          title: const Text('SolusCRT Saude'),
          backgroundColor: const Color(0xFF04131F),
          foregroundColor: Colors.white,
        ),
        SliverPadding(
          padding: const EdgeInsets.fromLTRB(18, 6, 18, 28),
          sliver: SliverList(
            delegate: SliverChildListDelegate(
              [
                _HeroCard(
                  onPrimary: () {
                    Navigator.of(context).push(
                      MaterialPageRoute(builder: (_) => const TelaSintomas()),
                    );
                  },
                  onSecondary: () {
                    Navigator.of(context).push(
                      MaterialPageRoute(builder: (_) => const TelaMapa()),
                    );
                  },
                ),
                const SizedBox(height: 16),
                if (!loading)
                  _ModoMonitoramentoCard(
                    modo: modoMonitoramento,
                    regiaoBaseLabel: regiaoBase == null
                        ? 'Ainda aprendendo sua regiao principal'
                        : '${regiaoBase!['bairro'] ?? 'Base'} • ${regiaoBase!['cidade']} / ${regiaoBase!['estado']}',
                    localAtualLabel: localAtual.isEmpty
                        ? 'Sem leitura atual'
                        : '${localAtual['bairro'] ?? 'Atual'} • ${localAtual['cidade']} / ${localAtual['estado']}',
                    estaForaDaBase: estaForaDaBase,
                    onChanged: _alterarModo,
                  ),
                if (!loading) const SizedBox(height: 16),
                if (loading)
                  const Card(
                    child: Padding(
                      padding: EdgeInsets.all(20),
                      child: Center(child: CircularProgressIndicator()),
                    ),
                  ),
                if (!loading)
                  _LiveMetricsCard(
                    registros24h: resumoData['registros_24h'] ?? 0,
                    registros7d: resumoData['registros_7d'] ?? 0,
                    crescimento7d: resumoData['crescimento_7d'] ?? 0,
                    localLabel: local.isEmpty
                        ? 'Localizacao pendente'
                        : '${local['cidade']} / ${local['estado']}',
                    regiaoBaseLabel: regiaoBase == null
                        ? 'Aprendendo sua regiao principal'
                        : '${regiaoBase!['bairro'] ?? 'Base'} • ${regiaoBase!['cidade']} / ${regiaoBase!['estado']}',
                    localNivel: radar['nivel']?.toString() ?? 'baixo',
                    topDoencas: doencas,
                    semaforo: semaforo,
                  ),
                const SizedBox(height: 16),
                if (!loading) _PublicAlertCard(alerta: alertaPublico),
                const SizedBox(height: 16),
                if (!loading && alertasPublicos.isNotEmpty)
                  _GovernmentAlertsCard(
                    alertas: alertasPublicos,
                    onOpenAlert: (alerta) => _abrirAlertaSeExistir(
                      [alerta],
                      permitirLembrarDepois: false,
                    ),
                  ),
                if (!loading && alertasPublicos.isNotEmpty)
                  const SizedBox(height: 16),
                if (!loading) _GuidanceCard(orientacao: orientacao),
                const SizedBox(height: 16),
                const _ValueCard(
                  title: 'Monitoramento regional para a populacao',
                  body:
                      'O app mostra sinais relevantes da sua regiao, como variacao de sintomas, doencas predominantes e hotspots recentes.',
                  icon: Icons.insights,
                ),
                const SizedBox(height: 16),
                const _ValueCard(
                  title: 'Privacidade e confianca do dado',
                  body:
                      'Os envios sao anonimos e passam por protecoes contra repeticao e abuso para manter a leitura epidemiologica mais confiavel.',
                  icon: Icons.verified_user,
                ),
                const SizedBox(height: 16),
                const _ValueCard(
                  title: 'Informacao simples e responsavel',
                  body:
                      'Acompanhe o radar local, o mapa publico e comunicados oficiais para tomar decisoes melhores no seu dia a dia.',
                  icon: Icons.language,
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }
}

class _LiveMetricsCard extends StatelessWidget {
  const _LiveMetricsCard({
    required this.registros24h,
    required this.registros7d,
    required this.crescimento7d,
    required this.localLabel,
    required this.regiaoBaseLabel,
    required this.localNivel,
    required this.topDoencas,
    required this.semaforo,
  });

  final int registros24h;
  final int registros7d;
  final dynamic crescimento7d;
  final String localLabel;
  final String regiaoBaseLabel;
  final String localNivel;
  final List<dynamic> topDoencas;
  final Map<String, dynamic> semaforo;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(18),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'Semaforo epidemiologico',
              style: TextStyle(
                color: Colors.white,
                fontSize: 18,
                fontWeight: FontWeight.w800,
              ),
            ),
            const SizedBox(height: 12),
            _SemaforoBanner(semaforo: semaforo),
            const SizedBox(height: 14),
            Wrap(
              spacing: 10,
              runSpacing: 10,
              children: [
                _MetricPill(label: 'Registros 24h', value: '$registros24h'),
                _MetricPill(label: 'Registros 7d', value: '$registros7d'),
                _MetricPill(label: 'Crescimento', value: '$crescimento7d%'),
                _MetricPill(label: 'Regiao-base', value: regiaoBaseLabel),
                _MetricPill(label: 'Leitura atual', value: localLabel),
                _MetricPill(label: 'Nivel local', value: localNivel),
              ],
            ),
            const SizedBox(height: 14),
            Text(
              'Principais sinais recentes da sua regiao',
              style: TextStyle(
                color: Colors.white.withValues(alpha: 0.9),
                fontWeight: FontWeight.w600,
              ),
            ),
            const SizedBox(height: 10),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: topDoencas.take(5).map((item) {
                final data = item as Map<String, dynamic>;
                return Chip(
                  backgroundColor: const Color(0xFF16394F),
                  label: Text(
                    '${data['grupo']} ${data['percentual']}%',
                    style: const TextStyle(color: Colors.white),
                  ),
                );
              }).toList(),
            ),
          ],
        ),
      ),
    );
  }
}

class _ModoMonitoramentoCard extends StatelessWidget {
  const _ModoMonitoramentoCard({
    required this.modo,
    required this.regiaoBaseLabel,
    required this.localAtualLabel,
    required this.estaForaDaBase,
    required this.onChanged,
  });

  final String modo;
  final String regiaoBaseLabel;
  final String localAtualLabel;
  final bool estaForaDaBase;
  final ValueChanged<String> onChanged;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(18),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'Territorio monitorado',
              style: TextStyle(
                color: Colors.white,
                fontSize: 18,
                fontWeight: FontWeight.w800,
              ),
            ),
            const SizedBox(height: 8),
            SegmentedButton<String>(
              showSelectedIcon: false,
              segments: const [
                ButtonSegment<String>(value: 'base', label: Text('Minha base')),
                ButtonSegment<String>(
                    value: 'atual', label: Text('Onde estou')),
              ],
              selected: {modo},
              onSelectionChanged: (values) => onChanged(values.first),
            ),
            const SizedBox(height: 12),
            Text(
              'Regiao-base: $regiaoBaseLabel',
              style: const TextStyle(color: Color(0xFF9CC4DB)),
            ),
            const SizedBox(height: 4),
            Text(
              'Leitura atual: $localAtualLabel',
              style: const TextStyle(color: Color(0xFF9CC4DB)),
            ),
            if (estaForaDaBase) ...[
              const SizedBox(height: 10),
              Container(
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: const Color(0xFF4B2E12),
                  borderRadius: BorderRadius.circular(16),
                ),
                child: const Text(
                  'Voce esta fora da sua regiao-base. O app pode acompanhar sua base principal ou a localizacao atual.',
                  style: TextStyle(color: Colors.white, height: 1.35),
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _PublicAlertCard extends StatelessWidget {
  const _PublicAlertCard({required this.alerta});

  final Map<String, dynamic> alerta;

  @override
  Widget build(BuildContext context) {
    final gravidade = (alerta['gravidade'] ?? 'leve').toString();
    final color = switch (gravidade) {
      'critica' => const Color(0xFFB83232),
      'alta' => const Color(0xFFB56A18),
      'moderada' => const Color(0xFF8A6A14),
      _ => const Color(0xFF165C46),
    };

    return Container(
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: color,
        borderRadius: BorderRadius.circular(24),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'Alerta publico',
            style: TextStyle(
              color: Colors.white70,
              fontSize: 12,
              fontWeight: FontWeight.w700,
            ),
          ),
          const SizedBox(height: 8),
          Text(
            alerta['titulo']?.toString() ?? 'Sem alerta relevante',
            style: const TextStyle(
              color: Colors.white,
              fontSize: 20,
              fontWeight: FontWeight.w800,
            ),
          ),
          const SizedBox(height: 8),
          Text(
            alerta['mensagem']?.toString() ?? '',
            style: const TextStyle(color: Colors.white, height: 1.45),
          ),
        ],
      ),
    );
  }
}

class _GuidanceCard extends StatelessWidget {
  const _GuidanceCard({required this.orientacao});

  final Map<String, dynamic> orientacao;

  @override
  Widget build(BuildContext context) {
    final acoes = orientacao['acoes'] as List<dynamic>? ?? [];
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(18),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'Orientacao para a populacao',
              style: TextStyle(
                color: Colors.white,
                fontSize: 18,
                fontWeight: FontWeight.w800,
              ),
            ),
            const SizedBox(height: 8),
            Text(
              orientacao['titulo']?.toString() ?? 'Monitoramento ativo',
              style: const TextStyle(
                color: Color(0xFF39D0C3),
                fontWeight: FontWeight.w700,
              ),
            ),
            const SizedBox(height: 8),
            Text(
              orientacao['resumo']?.toString() ?? '',
              style: const TextStyle(color: Color(0xFF9CC4DB), height: 1.45),
            ),
            const SizedBox(height: 12),
            ...acoes.map((acao) => Padding(
                  padding: const EdgeInsets.only(bottom: 8),
                  child: Row(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Padding(
                        padding: EdgeInsets.only(top: 3),
                        child: Icon(Icons.check_circle,
                            size: 16, color: Color(0xFF39D0C3)),
                      ),
                      const SizedBox(width: 8),
                      Expanded(
                        child: Text(
                          acao.toString(),
                          style:
                              const TextStyle(color: Colors.white, height: 1.4),
                        ),
                      ),
                    ],
                  ),
                )),
          ],
        ),
      ),
    );
  }
}

class _GovernmentAlertsCard extends StatelessWidget {
  const _GovernmentAlertsCard({
    required this.alertas,
    required this.onOpenAlert,
  });

  final List<dynamic> alertas;
  final ValueChanged<Map<String, dynamic>> onOpenAlert;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(18),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text(
              'Comunicados do governo',
              style: TextStyle(
                color: Colors.white,
                fontSize: 18,
                fontWeight: FontWeight.w800,
              ),
            ),
            const SizedBox(height: 12),
            ...alertas.take(3).map((item) {
              final alerta = item as Map<String, dynamic>;
              final recorte = [
                alerta['bairro']?.toString(),
                alerta['cidade']?.toString(),
                alerta['estado']?.toString(),
              ].where((item) => item != null && item.isNotEmpty).join(' / ');
              return Padding(
                padding: const EdgeInsets.only(bottom: 12),
                child: InkWell(
                  borderRadius: BorderRadius.circular(18),
                  onTap: () => onOpenAlert(alerta),
                  child: Column(
                    children: [
                      Container(
                        padding: const EdgeInsets.all(14),
                        decoration: BoxDecoration(
                          color: const Color(0xFF132B3C),
                          borderRadius: BorderRadius.circular(18),
                          border: Border.all(
                            color:
                                const Color(0xFF39D0C3).withValues(alpha: 0.24),
                          ),
                        ),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Row(
                              children: [
                                const Icon(Icons.campaign_outlined,
                                    color: Color(0xFFFFD166)),
                                const SizedBox(width: 8),
                                Expanded(
                                  child: Text(
                                    alerta['titulo']?.toString() ??
                                        'Alerta publico',
                                    style: const TextStyle(
                                      color: Colors.white,
                                      fontWeight: FontWeight.w700,
                                    ),
                                  ),
                                ),
                              ],
                            ),
                            const SizedBox(height: 6),
                            Text(
                              alerta['mensagem']?.toString() ?? '',
                              style: const TextStyle(
                                  color: Color(0xFF9CC4DB), height: 1.4),
                            ),
                            if (recorte.isNotEmpty) ...[
                              const SizedBox(height: 6),
                              Text(
                                'Recorte: $recorte',
                                style: const TextStyle(
                                  color: Color(0xFFFFD166),
                                  fontSize: 12,
                                ),
                              ),
                            ],
                            const SizedBox(height: 8),
                            const Text(
                              'Toque para abrir o comunicado completo',
                              style: TextStyle(
                                color: Color(0xFF39D0C3),
                                fontSize: 12,
                              ),
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                ),
              );
            }),
          ],
        ),
      ),
    );
  }
}

class _SemaforoBanner extends StatelessWidget {
  const _SemaforoBanner({required this.semaforo});

  final Map<String, dynamic> semaforo;

  @override
  Widget build(BuildContext context) {
    final faixa = semaforo['faixa']?.toString() ?? 'Verde';
    final descricao = semaforo['descricao']?.toString() ?? '';
    final corHex = semaforo['cor']?.toString() ?? '#1DD1A1';
    final color = Color(int.parse(corHex.substring(1), radix: 16) + 0xFF000000);

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.18),
        border: Border.all(color: color.withValues(alpha: 0.6)),
        borderRadius: BorderRadius.circular(22),
      ),
      child: Row(
        children: [
          Container(
            width: 18,
            height: 18,
            decoration: BoxDecoration(color: color, shape: BoxShape.circle),
          ),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Faixa $faixa',
                  style: const TextStyle(
                      color: Colors.white, fontWeight: FontWeight.w800),
                ),
                const SizedBox(height: 4),
                Text(
                  descricao,
                  style:
                      const TextStyle(color: Color(0xFFBEE9FF), height: 1.35),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _MetricPill extends StatelessWidget {
  const _MetricPill({
    required this.label,
    required this.value,
  });

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      decoration: BoxDecoration(
        color: const Color(0xFF112E43),
        borderRadius: BorderRadius.circular(18),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            label,
            style: const TextStyle(color: Color(0xFF86AFC6), fontSize: 12),
          ),
          const SizedBox(height: 4),
          Text(
            value,
            style: const TextStyle(
              color: Colors.white,
              fontWeight: FontWeight.w700,
            ),
          ),
        ],
      ),
    );
  }
}

class _HeroCard extends StatelessWidget {
  const _HeroCard({
    required this.onPrimary,
    required this.onSecondary,
  });

  final VoidCallback onPrimary;
  final VoidCallback onSecondary;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(28),
        gradient: const LinearGradient(
          colors: [Color(0xFF12324B), Color(0xFF0A1B29)],
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
            decoration: BoxDecoration(
              color: Colors.white.withValues(alpha: 0.1),
              borderRadius: BorderRadius.circular(999),
            ),
            child: const Text(
              'Monitoramento publico de saude',
              style: TextStyle(
                color: Color(0xFFBEE9FF),
                fontSize: 12,
                fontWeight: FontWeight.w700,
              ),
            ),
          ),
          const SizedBox(height: 18),
          const Text(
            'Acompanhe sua regiao, envie sintomas anonimos e veja sinais de alerta do seu territorio.',
            style: TextStyle(
              fontSize: 28,
              height: 1.15,
              color: Colors.white,
              fontWeight: FontWeight.w800,
            ),
          ),
          const SizedBox(height: 12),
          const Text(
            'Veja sinais da sua regiao, acompanhe comunicados oficiais e contribua de forma anonima para o monitoramento de saude publica.',
            style: TextStyle(
              color: Color(0xFF9FC5D9),
              fontSize: 15,
              height: 1.5,
            ),
          ),
          const SizedBox(height: 22),
          Wrap(
            spacing: 10,
            runSpacing: 10,
            children: [
              FilledButton.icon(
                onPressed: onPrimary,
                icon: const Icon(Icons.add_chart),
                label: const Text('Registrar sintomas'),
              ),
              OutlinedButton.icon(
                onPressed: onSecondary,
                icon: const Icon(Icons.map_outlined),
                label: const Text('Abrir mapa publico'),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _ValueCard extends StatelessWidget {
  const _ValueCard({
    required this.title,
    required this.body,
    required this.icon,
  });

  final String title;
  final String body;
  final IconData icon;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(18),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: const Color(0xFF16394F),
                borderRadius: BorderRadius.circular(16),
              ),
              child: Icon(icon, color: const Color(0xFF39D0C3)),
            ),
            const SizedBox(width: 14),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    title,
                    style: const TextStyle(
                      color: Colors.white,
                      fontSize: 16,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                  const SizedBox(height: 6),
                  Text(
                    body,
                    style: const TextStyle(
                      color: Color(0xFF9CC4DB),
                      height: 1.45,
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}
