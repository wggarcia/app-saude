import 'package:flutter/material.dart';

import '../../servicos/alerta_inbox_service.dart';
import '../../servicos/location_service.dart';
import '../../servicos/public_api_service.dart';
import '../../servicos/push_service.dart';
import '../../servicos/regiao_base_service.dart';
import '../alertas/tela_alertas.dart';
import '../fontes/tela_fontes.dart';
import '../mapa/tela_mapa.dart';
import '../sintomas/tela_sintomas.dart';

class TelaHome extends StatefulWidget {
  const TelaHome({super.key});

  @override
  State<TelaHome> createState() => _TelaHomeState();
}

class _TelaHomeState extends State<TelaHome> {
  int currentIndex = 0;
  int _mapRefreshSeed = 0;
  bool _locationPrimerShown = false;

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
            title: const Text('Ativar localização do SolusCRT'),
            content: const Text(
              'O app precisa pedir permissão de localização ao iPhone para mostrar focos perto de você e enviar sintomas no município correto. Toque em Permitir quando o iPhone solicitar.',
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
      body: _pageForIndex(currentIndex),
      bottomNavigationBar: NavigationBar(
        height: 74,
        backgroundColor: const Color(0xFF0B2333),
        selectedIndex: currentIndex,
        onDestinationSelected: (value) {
          setState(() {
            currentIndex = value;
            if (value == 2) {
              _mapRefreshSeed++;
            }
          });
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

  Widget _pageForIndex(int index) {
    switch (index) {
      case 1:
        return TelaSintomas(
          onSintomasEnviados: () {
            if (!mounted) return;
            setState(() {
              currentIndex = 2;
              _mapRefreshSeed++;
            });
          },
        );
      case 2:
        return TelaMapa(key: ValueKey(_mapRefreshSeed));
      case 3:
        return const TelaAlertas();
      case 0:
      default:
        return const TelaPainelCidadao();
    }
  }
}

class TelaPainelCidadao extends StatefulWidget {
  const TelaPainelCidadao({super.key});

  @override
  State<TelaPainelCidadao> createState() => _TelaPainelCidadaoState();
}

class _TelaPainelCidadaoState extends State<TelaPainelCidadao>
    with WidgetsBindingObserver {
  Map<String, dynamic>? resumo;
  Map<String, dynamic>? radarSelecionado;
  Map<String, dynamic>? radarAtual;
  Map<String, dynamic>? regiaoBase;
  List<dynamic> alertasPublicos = const [];
  String modoMonitoramento = 'atual';
  bool loading = true;
  bool _refreshingInBackground = false;
  Set<String> _dismissedKeys = {};

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    PushService.alertaRecebido.addListener(_onPushAlerta);
    _load();
  }

  @override
  void dispose() {
    PushService.alertaRecebido.removeListener(_onPushAlerta);
    WidgetsBinding.instance.removeObserver(this);
    super.dispose();
  }

  void _onPushAlerta() {
    _refreshOnResume();
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      _refreshOnResume();
    }
  }

  Future<void> _refreshOnResume() async {
    if (_refreshingInBackground || !mounted) {
      return;
    }
    _refreshingInBackground = true;
    try {
      await _load();
    } finally {
      _refreshingInBackground = false;
    }
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
      final resumoFuture = PublicApiService.fetchResumo()
          .catchError((_) => <String, dynamic>{});
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
      final resumoData = await resumoFuture;
      var alertas = await PublicApiService.fetchAlertas(
        cidade: (radarPreferido['local'] as Map<String, dynamic>?)?['cidade']
            ?.toString(),
        estado: (radarPreferido['local'] as Map<String, dynamic>?)?['estado']
            ?.toString(),
        bairro: (radarPreferido['local'] as Map<String, dynamic>?)?['bairro']
            ?.toString(),
      );
      if (alertas.isEmpty) {
        alertas = await PublicApiService.fetchAlertas();
      }
      final dismissedKeys = await AlertaInboxService.loadRadarDismissedKeys();
      final alertasFiltrados = alertas.where((item) {
        return !dismissedKeys.contains(
          AlertaInboxService.alertKey(Map<String, dynamic>.from(item as Map)),
        );
      }).toList();
      if (!mounted) {
        return;
      }
      setState(() {
        resumo = resumoData;
        radarSelecionado = radarPreferido;
        radarAtual = radarAgora;
        regiaoBase = updatedBase;
        alertasPublicos = alertasFiltrados;
        _dismissedKeys = dismissedKeys;
        modoMonitoramento = modo;
        loading = false;
      });
      final pushLocal = radarAgora['local'] as Map<String, dynamic>? ?? {};
      await PushService.syncRegion(
        estado: pushLocal['estado']?.toString(),
        cidade: pushLocal['cidade']?.toString(),
        bairro: pushLocal['bairro']?.toString(),
      );
      await _notificarNovosAlertas(alertas);
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

  Future<void> _dismissAlerta(Map<String, dynamic> alerta) async {
    // Remove da UI imediatamente — obrigatório para o Dismissible não travar.
    final key = AlertaInboxService.alertKey(alerta);
    if (!mounted) return;
    setState(() {
      _dismissedKeys = {..._dismissedKeys, key};
      alertasPublicos = alertasPublicos.where((item) {
        return !_dismissedKeys.contains(
          AlertaInboxService.alertKey(Map<String, dynamic>.from(item as Map)),
        );
      }).toList();
    });
    // Persiste em background (sem bloquear a UI).
    await AlertaInboxService.dismissFromRadar(alerta);
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
    final casosPorEstado = resumo?['casos_por_estado'] as List<dynamic>? ?? [];
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
    final alertaPublicoFeatured = alertaPublico.isNotEmpty &&
            !_dismissedKeys.contains(AlertaInboxService.alertKey(alertaPublico))
        ? alertaPublico
        : null;
    final alertaPublicoEfetivo = alertaPublicoFeatured ??
        (alertasPublicos.isNotEmpty
            ? Map<String, dynamic>.from(alertasPublicos.first as Map)
            : const <String, dynamic>{});
    final orientacao =
        radarSelecionado?['orientacao_publica'] as Map<String, dynamic>? ??
            resumo?['orientacao_publica'] as Map<String, dynamic>? ??
            {};

    return CustomScrollView(
      slivers: [
        SliverAppBar.large(
          pinned: true,
          title: const Text('SolusCRT Saúde'),
          backgroundColor: const Color(0xFF04131F),
          foregroundColor: Colors.white,
          actions: [
            IconButton(
              tooltip: 'Fontes e referências',
              icon: const Icon(Icons.menu_book_outlined),
              onPressed: () {
                Navigator.of(context).push(
                  MaterialPageRoute(builder: (_) => const TelaFontes()),
                );
              },
            ),
          ],
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
                const FontesResumoCard(),
                const SizedBox(height: 16),
                if (!loading)
                  _ModoMonitoramentoCard(
                    modo: modoMonitoramento,
                    regiaoBaseLabel: regiaoBase == null
                        ? 'Ainda aprendendo sua região principal'
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
                        ? 'Localização pendente'
                        : '${local['cidade']} / ${local['estado']}',
                    regiaoBaseLabel: regiaoBase == null
                        ? 'Aprendendo sua região principal'
                        : '${regiaoBase!['bairro'] ?? 'Base'} • ${regiaoBase!['cidade']} / ${regiaoBase!['estado']}',
                    localNivel: radar['nivel']?.toString() ?? 'baixo',
                    topDoencas: doencas,
                    semaforo: semaforo,
                  ),
                if (!loading && casosPorEstado.isNotEmpty) ...[
                  const SizedBox(height: 16),
                  _CasosPorEstadoCard(
                    casosPorEstado: (resumo?['casos_por_estado_ativos'] as List<dynamic>?) ?? casosPorEstado,
                    totalNacional: resumoData['total_ativo_30d'] ?? resumoData['indice_ativo_30d'] ?? resumoData['registros_30d'] ?? 0,
                  ),
                ],
                const SizedBox(height: 16),
                if (!loading)
                  _PublicAlertCard(
                    alerta: alertaPublicoEfetivo,
                    onDismiss:
                        alertaPublicoEfetivo.isNotEmpty ? _dismissAlerta : null,
                  ),
                const SizedBox(height: 16),
                if (!loading && alertasPublicos.isNotEmpty)
                  _GovernmentAlertsCard(
                    alertas: alertasPublicos,
                    onOpenAlert: (alerta) => _abrirAlertaSeExistir(
                      [alerta],
                      permitirLembrarDepois: false,
                    ),
                    onDismiss: _dismissAlerta,
                  ),
                if (!loading && alertasPublicos.isNotEmpty)
                  const SizedBox(height: 16),
                if (!loading) _GuidanceCard(orientacao: orientacao),
                const SizedBox(height: 16),
                const _ValueCard(
                  title: 'Monitoramento regional para a população',
                  body:
                      'O app mostra sinais relevantes da sua região, como variação de sintomas, doenças predominantes e hotspots recentes.',
                  icon: Icons.insights,
                ),
                const SizedBox(height: 16),
                const _ValueCard(
                  title: 'Privacidade e confiança do dado',
                  body:
                      'Os envios são anônimos e passam por proteções contra repetição e abuso para manter a leitura epidemiológica mais confiável.',
                  icon: Icons.verified_user,
                ),
                const SizedBox(height: 16),
                const _ValueCard(
                  title: 'Informação simples e responsável',
                  body:
                      'Acompanhe o radar local, o mapa público e comunicados oficiais para tomar decisões melhores no seu dia a dia.',
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
              'Semáforo epidemiológico',
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
                _MetricPill(label: 'Região-base', value: regiaoBaseLabel),
                _MetricPill(label: 'Leitura atual', value: localLabel),
                _MetricPill(label: 'Nível local', value: localNivel),
              ],
            ),
            const SizedBox(height: 14),
            Text(
              'Principais sinais recentes da sua região',
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

class _CasosPorEstadoCard extends StatelessWidget {
  const _CasosPorEstadoCard({
    required this.casosPorEstado,
    required this.totalNacional,
  });

  final List<dynamic> casosPorEstado;
  final dynamic totalNacional;

  Color _corPorVolume(double frac) {
    if (frac >= 0.66) return const Color(0xFFFF6B6B);
    if (frac >= 0.33) return const Color(0xFFFF9B54);
    if (frac >= 0.12) return const Color(0xFFFFD166);
    return const Color(0xFF1DD1A1);
  }

  @override
  Widget build(BuildContext context) {
    final itens =
        casosPorEstado.map((e) => Map<String, dynamic>.from(e as Map)).toList();
    final maxTotal = itens.isEmpty
        ? 1
        : itens
            .map((e) => (e['total'] as num?)?.toInt() ?? 0)
            .reduce((a, b) => a > b ? a : b);
    final total = (totalNacional is num) ? (totalNacional as num).toInt() : 0;

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(18),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Icon(Icons.public, color: Color(0xFF39D0C3), size: 22),
                const SizedBox(width: 8),
                const Expanded(
                  child: Text(
                    'Casos por estado',
                    style: TextStyle(
                      color: Colors.white,
                      fontSize: 18,
                      fontWeight: FontWeight.w800,
                    ),
                  ),
                ),
                Container(
                  padding:
                      const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                  decoration: BoxDecoration(
                    color: const Color(0xFF16394F),
                    borderRadius: BorderRadius.circular(999),
                  ),
                  child: Text(
                    '$total no Brasil',
                    style: const TextStyle(
                      color: Color(0xFF9CC4DB),
                      fontWeight: FontWeight.w700,
                      fontSize: 12,
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 4),
            Text(
              '${itens.length} estados com sinais ativos (30 dias)',
              style: const TextStyle(color: Color(0xFF77A0B8), fontSize: 12),
            ),
            const SizedBox(height: 14),
            ...itens.take(12).map((e) {
              final uf = e['uf']?.toString() ?? '--';
              final nome = e['estado']?.toString() ?? '';
              final qtd = (e['total'] as num?)?.toInt() ?? 0;
              final pct = (e['percentual'] as num?)?.toDouble() ?? 0.0;
              final frac = maxTotal > 0 ? qtd / maxTotal : 0.0;
              final cor = _corPorVolume(frac);
              return Padding(
                padding: const EdgeInsets.only(bottom: 10),
                child: Row(
                  children: [
                    SizedBox(
                      width: 34,
                      child: Text(
                        uf,
                        style: TextStyle(
                          color: cor,
                          fontWeight: FontWeight.w900,
                          fontSize: 14,
                        ),
                      ),
                    ),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Row(
                            mainAxisAlignment: MainAxisAlignment.spaceBetween,
                            children: [
                              Text(
                                nome,
                                style: const TextStyle(
                                  color: Color(0xFFCDE3F0),
                                  fontSize: 12.5,
                                  fontWeight: FontWeight.w600,
                                ),
                              ),
                              Text(
                                '$qtd  ·  ${pct.toStringAsFixed(0)}%',
                                style: const TextStyle(
                                  color: Colors.white,
                                  fontSize: 12.5,
                                  fontWeight: FontWeight.w800,
                                ),
                              ),
                            ],
                          ),
                          const SizedBox(height: 5),
                          ClipRRect(
                            borderRadius: BorderRadius.circular(999),
                            child: LinearProgressIndicator(
                              value: frac.clamp(0.04, 1.0),
                              minHeight: 7,
                              backgroundColor: const Color(0xFF0E2A3A),
                              valueColor: AlwaysStoppedAnimation<Color>(cor),
                            ),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              );
            }),
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
              'Território monitorado',
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
              'Região-base: $regiaoBaseLabel',
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
                  'Você está fora da sua região-base. O app pode acompanhar sua base principal ou a localização atual.',
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
  const _PublicAlertCard({
    required this.alerta,
    this.onDismiss,
  });

  final Map<String, dynamic> alerta;
  final ValueChanged<Map<String, dynamic>>? onDismiss;

  @override
  Widget build(BuildContext context) {
    final gravidade = (alerta['gravidade'] ?? 'leve').toString();
    final color = switch (gravidade) {
      'critica' => const Color(0xFFB83232),
      'alta' => const Color(0xFFB56A18),
      'moderada' => const Color(0xFF8A6A14),
      _ => const Color(0xFF165C46),
    };
    final temConteudo = alerta.isNotEmpty && alerta['titulo'] != null;

    return Stack(
      children: [
        Container(
          padding: const EdgeInsets.all(18),
          decoration: BoxDecoration(
            color: color,
            borderRadius: BorderRadius.circular(24),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              const Text(
                'Alerta público',
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
        ),
        if (temConteudo && onDismiss != null)
          Positioned(
            top: 8,
            right: 8,
            child: GestureDetector(
              onTap: () => onDismiss!(alerta),
              child: Container(
                padding: const EdgeInsets.all(5),
                decoration: BoxDecoration(
                  color: Colors.black26,
                  borderRadius: BorderRadius.circular(999),
                ),
                child: const Icon(
                  Icons.close,
                  color: Colors.white70,
                  size: 15,
                ),
              ),
            ),
          ),
      ],
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
              'Orientação para a população',
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
    required this.onDismiss,
  });

  final List<dynamic> alertas;
  final ValueChanged<Map<String, dynamic>> onOpenAlert;
  final ValueChanged<Map<String, dynamic>> onDismiss;

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
              final itemKey = ValueKey(
                (alerta['id'] ?? alerta['titulo'] ?? Object()).toString(),
              );
              final recorte = [
                alerta['bairro']?.toString(),
                alerta['cidade']?.toString(),
                alerta['estado']?.toString(),
              ].where((e) => e != null && e.isNotEmpty).join(' / ');
              return Padding(
                padding: const EdgeInsets.only(bottom: 12),
                child: Dismissible(
                  key: itemKey,
                  direction: DismissDirection.endToStart,
                  onDismissed: (_) => onDismiss(alerta),
                  background: Container(
                    alignment: Alignment.centerRight,
                    padding: const EdgeInsets.symmetric(horizontal: 20),
                    decoration: BoxDecoration(
                      color: const Color(0xFF8B1A1A),
                      borderRadius: BorderRadius.circular(18),
                    ),
                    child: const Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        Icon(Icons.delete_outline,
                            color: Colors.white, size: 22),
                        SizedBox(height: 4),
                        Text(
                          'Apagar',
                          style: TextStyle(
                              color: Colors.white,
                              fontSize: 11,
                              fontWeight: FontWeight.w700),
                        ),
                      ],
                    ),
                  ),
                  child: InkWell(
                    borderRadius: BorderRadius.circular(18),
                    onTap: () => onOpenAlert(alerta),
                    child: Container(
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
                                      'Alerta público',
                                  style: const TextStyle(
                                    color: Colors.white,
                                    fontWeight: FontWeight.w700,
                                  ),
                                ),
                              ),
                              GestureDetector(
                                onTap: () => onDismiss(alerta),
                                child: const Padding(
                                  padding: EdgeInsets.only(left: 8),
                                  child: Icon(
                                    Icons.close,
                                    color: Color(0xFF6A8FA8),
                                    size: 18,
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
                            'Toque para abrir · deslize para apagar',
                            style: TextStyle(
                              color: Color(0xFF39D0C3),
                              fontSize: 12,
                            ),
                          ),
                        ],
                      ),
                    ),
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
    final _hex = corHex.startsWith('#') && corHex.length == 7 ? corHex.substring(1) : '1DD1A1';
    final color = Color((int.tryParse(_hex, radix: 16) ?? 0x1DD1A1) + 0xFF000000);

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
              'Monitoramento público de saúde',
              style: TextStyle(
                color: Color(0xFFBEE9FF),
                fontSize: 12,
                fontWeight: FontWeight.w700,
              ),
            ),
          ),
          const SizedBox(height: 18),
          const Text(
            'Acompanhe sua região, envie sintomas de forma anônima e veja sinais de alerta do seu território.',
            style: TextStyle(
              fontSize: 28,
              height: 1.15,
              color: Colors.white,
              fontWeight: FontWeight.w800,
            ),
          ),
          const SizedBox(height: 12),
          const Text(
            'Veja sinais da sua região, acompanhe comunicados oficiais e contribua de forma anônima para o monitoramento de saúde pública.',
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
                label: const Text('Abrir mapa público'),
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
