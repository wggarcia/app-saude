import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';

import '../../servicos/location_service.dart';
import '../../servicos/public_api_service.dart';
import '../../servicos/regiao_base_service.dart';

class TelaMapa extends StatefulWidget {
  const TelaMapa({super.key});

  @override
  State<TelaMapa> createState() => _TelaMapaState();
}

class _TelaMapaState extends State<TelaMapa> {
  List<dynamic> hotspots = const [];
  Map<String, dynamic>? radarLocal;
  Map<String, dynamic>? radarAtual;
  Map<String, dynamic>? regiaoBase;
  String modoMonitoramento = 'base';
  bool loading = true;
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

      if (!mounted) {
        return;
      }
      setState(() {
        hotspots = mapa;
        radarLocal = radarPreferido;
        this.radarAtual = radarAtual;
        regiaoBase = updatedBase;
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

  @override
  Widget build(BuildContext context) {
    final center = regiaoBase != null
        ? LatLng(
            (regiaoBase!['latitude'] as num).toDouble(),
            (regiaoBase!['longitude'] as num).toDouble(),
          )
        : hotspots.isNotEmpty
            ? LatLng(
                (hotspots.first['latitude'] as num).toDouble(),
                (hotspots.first['longitude'] as num).toDouble(),
              )
            : const LatLng(-14.235, -51.9253);
    final localAtual = radarAtual?['local'] as Map<String, dynamic>? ?? {};
    final estaForaDaBase = RegiaoBaseService.estaForaDaRegiaoBase(
      regiaoBase: regiaoBase,
      localAtual: localAtual,
    );
    final zoom = regiaoBase != null || hotspots.isNotEmpty ? 10.2 : 4.2;
    final markers = hotspots
        .map(
          (item) => Marker(
            width: 120,
            height: 70,
            point: LatLng(
              (item['latitude'] as num).toDouble(),
              (item['longitude'] as num).toDouble(),
            ),
            child: _HotspotMarker(item: item as Map<String, dynamic>),
          ),
        )
        .toList();

    return Scaffold(
      appBar: AppBar(
        title: const Text('Mapa publico da sua regiao'),
        actions: [
          IconButton(
            onPressed: _load,
            icon: const Icon(Icons.refresh),
          ),
        ],
      ),
      body: loading
          ? const Center(child: CircularProgressIndicator())
          : Column(
              children: [
                if (notice != null)
                  Padding(
                    padding: const EdgeInsets.fromLTRB(16, 8, 16, 4),
                    child: _NoticeCard(message: notice!),
                  ),
                if (radarLocal != null)
                  Padding(
                    padding: const EdgeInsets.fromLTRB(16, 8, 16, 10),
                    child: _RadarCard(
                      radarLocal: radarLocal!,
                      regiaoBase: regiaoBase,
                      localAtual: localAtual,
                      modoMonitoramento: modoMonitoramento,
                      estaForaDaBase: estaForaDaBase,
                      onChangedModo: _alterarModo,
                    ),
                  ),
                Expanded(
                  child: FlutterMap(
                    options: MapOptions(
                      initialCenter: center,
                      initialZoom: zoom,
                    ),
                    children: [
                      TileLayer(
                        urlTemplate:
                            'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
                        userAgentPackageName: 'com.soluscrt.saude',
                      ),
                      MarkerLayer(markers: markers),
                    ],
                  ),
                ),
              ],
            ),
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
        children: [
          Container(
            padding: const EdgeInsets.all(8),
            decoration: BoxDecoration(
              color: const Color(0xFFE85D5D),
              borderRadius: BorderRadius.circular(999),
              boxShadow: const [
                BoxShadow(
                  color: Color(0x55E85D5D),
                  blurRadius: 18,
                  spreadRadius: 6,
                ),
              ],
            ),
            child: const Icon(Icons.warning_amber_rounded, color: Colors.white),
          ),
          const SizedBox(height: 4),
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
            decoration: BoxDecoration(
              color: const Color(0xCC04131F),
              borderRadius: BorderRadius.circular(12),
            ),
            child: Text(
              '${item['indice_ativo'] ?? item['total']}',
              style: const TextStyle(
                color: Colors.white,
                fontWeight: FontWeight.w700,
              ),
            ),
          ),
        ],
      ),
    );
  }
}
