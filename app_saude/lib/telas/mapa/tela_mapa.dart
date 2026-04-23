import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';

import '../../config.dart';
import '../../servicos/location_service.dart';
import '../../servicos/public_api_service.dart';
import '../../servicos/regiao_base_service.dart';

class TelaMapa extends StatefulWidget {
  const TelaMapa({super.key});

  @override
  State<TelaMapa> createState() => _TelaMapaState();
}

class _TelaMapaState extends State<TelaMapa> {
  final MapController _mapController = MapController();
  List<dynamic> hotspots = const [];
  Map<String, dynamic>? radarLocal;
  Map<String, dynamic>? radarAtual;
  Map<String, dynamic>? regiaoBase;
  LocationSnapshot? localizacaoAtual;
  List<dynamic> alertasPublicos = const [];
  String modoMonitoramento = 'base';
  bool loading = true;
  bool locating = false;
  String? notice;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<Map<String, dynamic>> _resolverRadarPreferido({
    required String modo,
    required Map<String, dynamic> radarAtual,
    required Map<String, dynamic>? base,
  }) async {
    final localAtual = radarAtual['local'] as Map<String, dynamic>? ?? {};
    final cidade = modo == 'base'
        ? (base?['cidade'] ?? localAtual['cidade'])?.toString()
        : localAtual['cidade']?.toString();
    final estado = modo == 'base'
        ? (base?['estado'] ?? localAtual['estado'])?.toString()
        : localAtual['estado']?.toString();
    final bairro = modo == 'base'
        ? (base?['bairro'] ?? localAtual['bairro'])?.toString()
        : localAtual['bairro']?.toString();

    try {
      return await PublicApiService.fetchRadarLocal(
          cidade: cidade, estado: estado, bairro: bairro);
    } catch (_) {
      return radarAtual;
    }
  }

  Future<void> _load() async {
    setState(() {
      loading = true;
      notice = null;
    });
    try {
      final modo = await RegiaoBaseService.obterModoMonitoramento();
      final base = await RegiaoBaseService.obterRegiaoBase();
      final location = await LocationService.getBestEffortLocation(
        fallbackRegion: base,
      );
      final radarAtual = await PublicApiService.fetchRadarLocal(
        latitude: location.latitude,
        longitude: location.longitude,
      );
      if (location.source == 'current') {
        await RegiaoBaseService.registrarObservacao(
          local: radarAtual['local'] as Map<String, dynamic>? ?? {},
          latitude: location.latitude,
          longitude: location.longitude,
        );
      }
      final updatedBase = await RegiaoBaseService.obterRegiaoBase();
      final radarPreferido = await _resolverRadarPreferido(
        modo: modo,
        radarAtual: radarAtual,
        base: updatedBase,
      );
      final localPreferido =
          radarPreferido['local'] as Map<String, dynamic>? ?? {};
      List<dynamic> mapa;
      List<dynamic> alertas;
      try {
        mapa = await PublicApiService.fetchMapa(
          cidade: localPreferido['cidade']?.toString(),
          estado: localPreferido['estado']?.toString(),
        );
        if (mapa.isEmpty) {
          mapa = await PublicApiService.fetchMapa();
        }
      } catch (_) {
        mapa = const [];
      }
      try {
        alertas = await PublicApiService.fetchAlertas(
          cidade: localPreferido['cidade']?.toString(),
          estado: localPreferido['estado']?.toString(),
          bairro: localPreferido['bairro']?.toString(),
        );
      } catch (_) {
        alertas = const [];
      }

      if (!mounted) {
        return;
      }
      setState(() {
        hotspots = mapa;
        radarLocal = radarPreferido;
        this.radarAtual = radarAtual;
        regiaoBase = updatedBase;
        localizacaoAtual = location.source == 'current' ? location : null;
        alertasPublicos = alertas;
        modoMonitoramento = modo;
        loading = false;
        notice = mapa.isEmpty
            ? 'Ainda nao ha focos publicos recentes para este recorte. O mapa continua acompanhando sua regiao.'
            : null;
      });
    } catch (err) {
      if (!mounted) {
        return;
      }
      final fallback = await _carregarMapaBasico();
      setState(() {
        hotspots = fallback;
        radarLocal = null;
        radarAtual = null;
        regiaoBase = null;
        localizacaoAtual = null;
        alertasPublicos = const [];
        notice =
            'Nao foi possivel atualizar o radar local agora. O mapa publico continua disponivel para consulta.';
        loading = false;
      });
    }
  }

  Future<List<dynamic>> _carregarMapaBasico() async {
    try {
      return await PublicApiService.fetchMapa();
    } catch (_) {
      return const [];
    }
  }

  Future<void> _alterarModo(String modo) async {
    if (modoMonitoramento == modo) {
      return;
    }
    await RegiaoBaseService.salvarModoMonitoramento(modo);
    await _load();
  }

  Future<void> _centralizarMinhaLocalizacao() async {
    setState(() => locating = true);
    try {
      final location = await LocationService.getCurrentLocationForSubmission();
      final point = LatLng(location.latitude, location.longitude);
      if (!mounted) {
        return;
      }
      setState(() => localizacaoAtual = location);
      _mapController.move(point, 16.2);
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Localizacao atual centralizada no mapa.'),
          duration: Duration(seconds: 3),
        ),
      );
    } catch (_) {
      if (!mounted) {
        return;
      }
      final abrir = await showDialog<bool>(
            context: context,
            builder: (context) => AlertDialog(
              title: const Text('GPS indisponivel'),
              content: const Text(
                'Nao consegui acessar sua localizacao exata agora. No simulador do Xcode, configure uma localizacao em Debug > Simulate Location. No iPhone real, confira se a permissao de localizacao esta ativa.',
              ),
              actions: [
                TextButton(
                  onPressed: () => Navigator.pop(context, false),
                  child: const Text('Fechar'),
                ),
                FilledButton(
                  onPressed: () => Navigator.pop(context, true),
                  child: const Text('Abrir ajustes'),
                ),
              ],
            ),
          ) ??
          false;
      if (abrir) {
        await LocationService.abrirAjustesLocalizacao();
      }
    } finally {
      if (mounted) {
        setState(() => locating = false);
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final center = hotspots.isNotEmpty
        ? LatLng(
            (hotspots.first['latitude'] as num).toDouble(),
            (hotspots.first['longitude'] as num).toDouble(),
          )
        : regiaoBase != null
            ? LatLng(
                (regiaoBase!['latitude'] as num).toDouble(),
                (regiaoBase!['longitude'] as num).toDouble(),
              )
            : const LatLng(-14.235, -51.9253);
    final localAtual = radarAtual?['local'] as Map<String, dynamic>? ?? {};
    final estaForaDaBase = RegiaoBaseService.estaForaDaRegiaoBase(
      regiaoBase: regiaoBase,
      localAtual: localAtual,
    );
    final zoom = regiaoBase != null || hotspots.isNotEmpty ? 10.2 : 4.2;
    final userPoint = localizacaoAtual == null
        ? null
        : LatLng(localizacaoAtual!.latitude, localizacaoAtual!.longitude);
    final circles = hotspots.whereType<Map>().map((raw) {
      final item = Map<String, dynamic>.from(raw);
      final visual = _FocusVisual.fromItem(item);
      final total = (item['indice_ativo'] as num?)?.toDouble() ??
          (item['total'] as num?)?.toDouble() ??
          1;
      return CircleMarker(
        point: LatLng(
          (item['latitude'] as num).toDouble(),
          (item['longitude'] as num).toDouble(),
        ),
        radius: (42 + total.clamp(1, 80) * 1.8).clamp(46, 150).toDouble(),
        color: visual.color.withValues(alpha: 0.18),
        borderColor: visual.color.withValues(alpha: 0.42),
        borderStrokeWidth: 2,
      );
    }).toList();
    final markers = hotspots
        .map(
          (item) => Marker(
            width: 104,
            height: 104,
            point: LatLng(
              (item['latitude'] as num).toDouble(),
              (item['longitude'] as num).toDouble(),
            ),
            child: _HotspotMarker(item: item as Map<String, dynamic>),
          ),
        )
        .toList();
    if (userPoint != null) {
      markers.add(
        Marker(
          width: 92,
          height: 92,
          point: userPoint,
          child: const _UserLocationMarker(),
        ),
      );
    }

    return Scaffold(
      appBar: AppBar(
        title: const Text('Mapa de risco'),
        actions: [
          IconButton(
            onPressed: _load,
            icon: const Icon(Icons.refresh),
          ),
        ],
      ),
      body: Stack(
        children: [
          Positioned.fill(
            child: FlutterMap(
              mapController: _mapController,
              options: MapOptions(
                initialCenter: center,
                initialZoom: zoom,
                interactionOptions: const InteractionOptions(
                  flags: InteractiveFlag.all & ~InteractiveFlag.rotate,
                ),
              ),
              children: [
                TileLayer(
                  urlTemplate:
                      'https://api.mapbox.com/styles/v1/mapbox/navigation-day-v1/tiles/256/{z}/{x}/{y}@2x?access_token=${Config.mapboxPublicToken}',
                  userAgentPackageName: 'com.soluscrt.saude',
                ),
                CircleLayer(circles: circles),
                MarkerLayer(markers: markers),
              ],
            ),
          ),
          if (loading)
            const Center(
              child: CircularProgressIndicator(color: Color(0xFF39D0C3)),
            )
          else ...[
            Positioned(
              top: 10,
              left: 16,
              right: 16,
              child: _MapHeroPanel(
                radarLocal: radarLocal,
                hotspots: hotspots,
                modoMonitoramento: modoMonitoramento,
                onChangedModo: _alterarModo,
              ),
            ),
            if (notice != null)
              Positioned(
                top: 114,
                left: 16,
                right: 16,
                child: _NoticeCard(message: notice!),
              ),
            if (alertasPublicos.isNotEmpty)
              Positioned(
                top: notice == null ? 114 : 196,
                left: 16,
                right: 16,
                child: _MapAlertBanner(
                  alerta: Map<String, dynamic>.from(
                    alertasPublicos.first as Map,
                  ),
                ),
              ),
            Positioned(
              top: alertasPublicos.isNotEmpty || notice != null ? 198 : 116,
              right: 16,
              child: _LocateButton(
                loading: locating,
                onPressed: _centralizarMinhaLocalizacao,
              ),
            ),
            if (radarLocal != null)
              Positioned(
                left: 12,
                right: 12,
                bottom: 12,
                child: ConstrainedBox(
                  constraints: BoxConstraints(
                    maxHeight: MediaQuery.of(context).size.height * 0.28,
                  ),
                  child: SingleChildScrollView(
                    child: _RadarCard(
                      radarLocal: radarLocal!,
                      regiaoBase: regiaoBase,
                      localAtual: localAtual,
                      modoMonitoramento: modoMonitoramento,
                      estaForaDaBase: estaForaDaBase,
                      onChangedModo: _alterarModo,
                    ),
                  ),
                ),
              ),
          ],
        ],
      ),
    );
  }
}

class _MapHeroPanel extends StatelessWidget {
  const _MapHeroPanel({
    required this.radarLocal,
    required this.hotspots,
    required this.modoMonitoramento,
    required this.onChangedModo,
  });

  final Map<String, dynamic>? radarLocal;
  final List<dynamic> hotspots;
  final String modoMonitoramento;
  final ValueChanged<String> onChangedModo;

  @override
  Widget build(BuildContext context) {
    final local = radarLocal?['local'] as Map<String, dynamic>? ?? {};
    final radar = radarLocal?['radar'] as Map<String, dynamic>? ?? {};
    final doencas = radarLocal?['doencas'] as List<dynamic>? ?? [];
    final principal = doencas.isNotEmpty
        ? (doencas.first as Map)['grupo']?.toString() ?? 'Monitoramento'
        : 'Monitoramento';
    return Container(
      padding: const EdgeInsets.fromLTRB(14, 12, 14, 12),
      decoration: BoxDecoration(
        color: const Color(0xF5FFFFFF),
        borderRadius: BorderRadius.circular(24),
        border: Border.all(color: const Color(0x5539D0C3)),
        boxShadow: const [
          BoxShadow(
            color: Color(0x33000000),
            blurRadius: 20,
            offset: Offset(0, 10),
          ),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisSize: MainAxisSize.min,
        children: [
          Row(
            children: [
              Container(
                width: 40,
                height: 40,
                decoration: BoxDecoration(
                  borderRadius: BorderRadius.circular(14),
                  gradient: const LinearGradient(
                    colors: [Color(0xFF39D0C3), Color(0xFF0B6B8A)],
                  ),
                ),
                child: const Icon(Icons.radar, color: Colors.white),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    const Text(
                      'Radar epidemiologico vivo',
                      style: TextStyle(
                        color: Color(0xFF082033),
                        fontWeight: FontWeight.w900,
                        fontSize: 16,
                      ),
                    ),
                    const SizedBox(height: 3),
                    Text(
                      '${local['cidade'] ?? 'Brasil'} / ${local['estado'] ?? 'BR'}',
                      style: const TextStyle(color: Color(0xFF436170)),
                    ),
                  ],
                ),
              ),
              Text(
                '${hotspots.length}',
                style: const TextStyle(
                  color: Color(0xFFE85F18),
                  fontSize: 24,
                  fontWeight: FontWeight.w900,
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          SegmentedButton<String>(
            showSelectedIcon: false,
            segments: const [
              ButtonSegment<String>(value: 'base', label: Text('Minha base')),
              ButtonSegment<String>(value: 'atual', label: Text('Onde estou')),
            ],
            selected: {modoMonitoramento},
            onSelectionChanged: (values) => onChangedModo(values.first),
          ),
          const SizedBox(height: 8),
          Text(
            '$principal | nivel ${radar['nivel']?.toString() ?? 'baixo'} | ${radar['registros_7d'] ?? 0} sinais em 7 dias',
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(
              color: Color(0xFF436170),
              fontWeight: FontWeight.w700,
            ),
          ),
        ],
      ),
    );
  }
}

class _LocateButton extends StatelessWidget {
  const _LocateButton({required this.loading, required this.onPressed});

  final bool loading;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    return Material(
      color: const Color(0xF7FFFFFF),
      shape: const CircleBorder(),
      elevation: 8,
      shadowColor: const Color(0x33000000),
      child: InkWell(
        customBorder: const CircleBorder(),
        onTap: loading ? null : onPressed,
        child: SizedBox(
          width: 54,
          height: 54,
          child: Center(
            child: loading
                ? const SizedBox(
                    width: 20,
                    height: 20,
                    child: CircularProgressIndicator(strokeWidth: 2.4),
                  )
                : const Icon(
                    Icons.my_location,
                    color: Color(0xFF0B6B8A),
                    size: 27,
                  ),
          ),
        ),
      ),
    );
  }
}

class _UserLocationMarker extends StatelessWidget {
  const _UserLocationMarker();

  @override
  Widget build(BuildContext context) {
    return Stack(
      alignment: Alignment.center,
      children: [
        Container(
          width: 70,
          height: 70,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: const Color(0xFF1A73E8).withValues(alpha: 0.16),
          ),
        ),
        Container(
          width: 34,
          height: 34,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: const Color(0xFF1A73E8).withValues(alpha: 0.28),
          ),
        ),
        Container(
          width: 20,
          height: 20,
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: const Color(0xFF1A73E8),
            border: Border.all(color: Colors.white, width: 4),
            boxShadow: const [
              BoxShadow(
                color: Color(0x55000000),
                blurRadius: 12,
                offset: Offset(0, 4),
              ),
            ],
          ),
        ),
      ],
    );
  }
}

class _NoticeCard extends StatelessWidget {
  const _NoticeCard({required this.message});

  final String message;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Icon(Icons.info_outline, color: Color(0xFF39D0C3)),
            const SizedBox(width: 10),
            Expanded(
              child: Text(
                message,
                style: const TextStyle(color: Color(0xFFBEE9FF), height: 1.35),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _MapAlertBanner extends StatelessWidget {
  const _MapAlertBanner({required this.alerta});

  final Map<String, dynamic> alerta;

  @override
  Widget build(BuildContext context) {
    final recorte = [
      alerta['bairro']?.toString(),
      alerta['cidade']?.toString(),
      alerta['estado']?.toString(),
    ].where((item) => item != null && item.isNotEmpty).join(' / ');

    return InkWell(
      borderRadius: BorderRadius.circular(22),
      onTap: () {
        showModalBottomSheet<void>(
          context: context,
          backgroundColor: const Color(0xFF0B2333),
          builder: (context) => Padding(
            padding: const EdgeInsets.all(22),
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  'Comunicado governamental',
                  style: TextStyle(color: Color(0xFFFFD166), fontSize: 13),
                ),
                const SizedBox(height: 8),
                Text(
                  alerta['titulo']?.toString() ?? 'Alerta publico',
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 20,
                    fontWeight: FontWeight.w800,
                  ),
                ),
                const SizedBox(height: 10),
                Text(
                  alerta['mensagem']?.toString() ?? '',
                  style: const TextStyle(
                    color: Color(0xFFBEE9FF),
                    height: 1.45,
                  ),
                ),
                if (recorte.isNotEmpty) ...[
                  const SizedBox(height: 10),
                  Text(
                    'Recorte: $recorte',
                    style: const TextStyle(
                      color: Color(0xFFFFD166),
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                ],
              ],
            ),
          ),
        );
      },
      child: Container(
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: const Color(0xFF3B2A12),
          borderRadius: BorderRadius.circular(22),
          border:
              Border.all(color: const Color(0xFFFFD166).withValues(alpha: 0.5)),
        ),
        child: Row(
          children: [
            const Icon(Icons.campaign_outlined, color: Color(0xFFFFD166)),
            const SizedBox(width: 10),
            Expanded(
              child: Text(
                alerta['titulo']?.toString() ?? 'Comunicado do governo',
                style: const TextStyle(
                  color: Colors.white,
                  fontWeight: FontWeight.w700,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _RadarCard extends StatelessWidget {
  const _RadarCard({
    required this.radarLocal,
    required this.regiaoBase,
    required this.localAtual,
    required this.modoMonitoramento,
    required this.estaForaDaBase,
    required this.onChangedModo,
  });

  final Map<String, dynamic> radarLocal;
  final Map<String, dynamic>? regiaoBase;
  final Map<String, dynamic> localAtual;
  final String modoMonitoramento;
  final bool estaForaDaBase;
  final ValueChanged<String> onChangedModo;

  @override
  Widget build(BuildContext context) {
    final local = radarLocal['local'] as Map<String, dynamic>? ?? {};
    final radar = radarLocal['radar'] as Map<String, dynamic>? ?? {};
    final doencas = radarLocal['doencas'] as List<dynamic>? ?? [];
    final semaforo = radarLocal['semaforo'] as Map<String, dynamic>? ?? {};
    final alerta = radarLocal['alerta_publico'] as Map<String, dynamic>? ?? {};
    final orientacao =
        radarLocal['orientacao_publica'] as Map<String, dynamic>? ?? {};
    final corHex = semaforo['cor']?.toString() ?? '#1DD1A1';
    final cor = Color(int.parse(corHex.substring(1), radix: 16) + 0xFF000000);

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              '${local['cidade'] ?? 'Cidade'} / ${local['estado'] ?? 'UF'}',
              style: const TextStyle(
                color: Colors.white,
                fontSize: 18,
                fontWeight: FontWeight.w700,
              ),
            ),
            const SizedBox(height: 6),
            if (regiaoBase != null)
              Padding(
                padding: const EdgeInsets.only(bottom: 8),
                child: Text(
                  'Regiao-base aprendida: ${regiaoBase!['bairro'] ?? 'Base'} • ${regiaoBase!['cidade']} / ${regiaoBase!['estado']}',
                  style: const TextStyle(color: Color(0xFF9CC4DB)),
                ),
              ),
            if (localAtual.isNotEmpty)
              Padding(
                padding: const EdgeInsets.only(bottom: 8),
                child: Text(
                  'Local atual: ${localAtual['bairro'] ?? 'Atual'} • ${localAtual['cidade']} / ${localAtual['estado']}',
                  style: const TextStyle(color: Color(0xFF9CC4DB)),
                ),
              ),
            SegmentedButton<String>(
              showSelectedIcon: false,
              segments: const [
                ButtonSegment<String>(value: 'base', label: Text('Minha base')),
                ButtonSegment<String>(
                    value: 'atual', label: Text('Onde estou')),
              ],
              selected: {modoMonitoramento},
              onSelectionChanged: (values) => onChangedModo(values.first),
            ),
            if (estaForaDaBase) ...[
              const SizedBox(height: 10),
              const Text(
                'Voce esta fora da sua regiao-base. Alterne para acompanhar sua base principal ou o territorio atual.',
                style: TextStyle(color: Color(0xFF9CC4DB), height: 1.35),
              ),
            ],
            const SizedBox(height: 10),
            Row(
              children: [
                Container(
                  width: 14,
                  height: 14,
                  decoration: BoxDecoration(color: cor, shape: BoxShape.circle),
                ),
                const SizedBox(width: 8),
                Text(
                  'Faixa ${semaforo['faixa'] ?? 'Verde'}',
                  style: const TextStyle(
                      color: Colors.white, fontWeight: FontWeight.w700),
                ),
              ],
            ),
            const SizedBox(height: 8),
            Text(
              'Nivel ${radar['nivel'] ?? 'baixo'} | ${radar['registros_7d'] ?? 0} registros em 7 dias | indice ativo 30d ${radar['indice_ativo_30d'] ?? radar['indice_ativo_7d'] ?? 0} | crescimento ${radar['crescimento_7d'] ?? 0}%',
              style: const TextStyle(color: Color(0xFF97BDD2)),
            ),
            const SizedBox(height: 12),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: doencas.take(4).map((item) {
                final data = item as Map<String, dynamic>;
                return Chip(
                  label: Text(
                    '${data['grupo']} ${data['percentual']}%',
                    style: const TextStyle(color: Colors.white),
                  ),
                  backgroundColor: const Color(0xFF16394F),
                );
              }).toList(),
            ),
            const SizedBox(height: 12),
            Text(
              alerta['titulo']?.toString() ?? '',
              style: const TextStyle(
                  color: Colors.white, fontWeight: FontWeight.w700),
            ),
            const SizedBox(height: 4),
            Text(
              alerta['mensagem']?.toString() ?? '',
              style: const TextStyle(color: Color(0xFF9CC4DB), height: 1.4),
            ),
            const SizedBox(height: 10),
            Text(
              orientacao['titulo']?.toString() ?? '',
              style: const TextStyle(
                  color: Color(0xFF39D0C3), fontWeight: FontWeight.w700),
            ),
          ],
        ),
      ),
    );
  }
}

class _HotspotMarker extends StatelessWidget {
  const _HotspotMarker({required this.item});

  final Map<String, dynamic> item;

  @override
  Widget build(BuildContext context) {
    final visual = _FocusVisual.fromItem(item);
    return GestureDetector(
      onTap: () {
        showModalBottomSheet<void>(
          context: context,
          backgroundColor: const Color(0xFF0B2333),
          builder: (context) {
            return Padding(
              padding: const EdgeInsets.all(20),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    '${item['bairro'] ?? 'Bairro'} - ${item['cidade']} / ${item['estado']}',
                    style: const TextStyle(
                      color: Colors.white,
                      fontSize: 18,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                  const SizedBox(height: 10),
                  Text(
                    'Focos recentes: ${item['total']}',
                    style: const TextStyle(color: Color(0xFF9CC4DB)),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    'Indice ativo: ${item['indice_ativo'] ?? item['total']} | participacao: ${item['percentual_ativo'] ?? 0}%',
                    style: const TextStyle(color: Color(0xFF9CC4DB)),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    'Faixa ${((item['semaforo'] as Map<String, dynamic>?)?['faixa'] ?? 'Verde')}',
                    style: const TextStyle(color: Color(0xFF9CC4DB)),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    'Doenca dominante: ${item['grupo_dominante']}',
                    style: const TextStyle(color: Color(0xFF9CC4DB)),
                  ),
                ],
              ),
            );
          },
        );
      },
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Container(
            width: 66,
            height: 66,
            decoration: BoxDecoration(
              shape: BoxShape.circle,
              color: Colors.white,
              border: Border.all(color: visual.color, width: 4),
              boxShadow: [
                BoxShadow(
                  color: visual.color.withValues(alpha: 0.55),
                  blurRadius: 28,
                  spreadRadius: 5,
                ),
                const BoxShadow(
                  color: Color(0x55000000),
                  blurRadius: 16,
                  offset: Offset(0, 8),
                ),
              ],
            ),
            child: Stack(
              clipBehavior: Clip.none,
              alignment: Alignment.center,
              children: [
                Positioned(
                  bottom: -12,
                  child: Transform.rotate(
                    angle: 0.785,
                    child: Container(
                      width: 20,
                      height: 20,
                      decoration: BoxDecoration(
                        color: visual.color,
                        borderRadius: BorderRadius.circular(4),
                      ),
                    ),
                  ),
                ),
                Positioned(
                  top: 9,
                  child: Icon(visual.icon, color: visual.color, size: 31),
                ),
                Positioned(
                  bottom: 8,
                  child: Text(
                    visual.shortLabel,
                    style: TextStyle(
                      color: Color.lerp(visual.color, Colors.black, 0.2),
                      fontSize: 10,
                      fontWeight: FontWeight.w900,
                      letterSpacing: 0.4,
                    ),
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 4),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
            decoration: BoxDecoration(
              color: const Color(0xEE04131F),
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: Colors.white.withValues(alpha: 0.18)),
            ),
            child: Text(
              '${visual.label} casos',
              style: const TextStyle(
                color: Colors.white,
                fontWeight: FontWeight.w700,
                fontSize: 11,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _FocusVisual {
  const _FocusVisual({
    required this.icon,
    required this.color,
    required this.label,
    required this.shortLabel,
  });

  final IconData icon;
  final Color color;
  final String label;
  final String shortLabel;

  static _FocusVisual fromItem(Map<String, dynamic> item) {
    final grupo = (item['grupo_dominante'] ?? '').toString().toLowerCase();
    final faixa = ((item['semaforo'] as Map<String, dynamic>?)?['faixa'] ?? '')
        .toString()
        .toLowerCase();
    final indice = item['indice_ativo'] ?? item['total'] ?? 0;
    final icon = switch (grupo) {
      String value when value.contains('covid') => Icons.coronavirus,
      String value when value.contains('resp') || value.contains('gripe') =>
        Icons.air,
      String value
          when value.contains('arb') ||
              value.contains('deng') ||
              value.contains('zika') ||
              value.contains('chik') =>
        Icons.bug_report,
      String value when value.contains('alert') => Icons.emergency,
      String value when value.contains('leve') => Icons.healing,
      _ => Icons.biotech,
    };
    final shortLabel = switch (grupo) {
      String value when value.contains('covid') => 'COVID',
      String value when value.contains('gripe') => 'GRIPE',
      String value when value.contains('resp') => 'RESP',
      String value when value.contains('deng') => 'DENG',
      String value when value.contains('zika') => 'ZIKA',
      String value when value.contains('chik') => 'CHIK',
      String value when value.contains('arb') => 'ARBO',
      String value when value.contains('leve') => 'LEVE',
      _ => 'FOCO',
    };
    final color = switch (faixa) {
      String value when value.contains('vermel') => const Color(0xFFE94747),
      String value when value.contains('laranja') => const Color(0xFFFF8A3D),
      String value when value.contains('amarel') => const Color(0xFFFFC857),
      _ => const Color(0xFF28C7B7),
    };
    return _FocusVisual(
      icon: icon,
      color: color,
      label: '$indice',
      shortLabel: shortLabel,
    );
  }
}
