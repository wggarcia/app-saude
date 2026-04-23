import 'package:flutter/material.dart';

import '../../servicos/location_service.dart';
import '../../servicos/public_api_service.dart';
import '../../servicos/regiao_base_service.dart';

class TelaSintomas extends StatefulWidget {
  const TelaSintomas({super.key});

  @override
  State<TelaSintomas> createState() => _TelaSintomasState();
}

class _TelaSintomasState extends State<TelaSintomas> {
  final Map<String, bool> sintomas = {
    'febre': false,
    'tosse': false,
    'dor_corpo': false,
    'cansaco': false,
    'falta_ar': false,
  };

  bool loading = false;
  Map<String, dynamic>? lastResult;

  Future<void> enviarDados() async {
    final selected = sintomas.values.where((value) => value).length;
    if (selected == 0) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Selecione ao menos um sintoma.')),
      );
      return;
    }

    setState(() => loading = true);
    try {
      final location = await _resolverLocalizacaoEnvio();
      if (location == null) {
        return;
      }
      final result = await PublicApiService.enviarSintomas(
        sintomas: sintomas,
        latitude: location.latitude,
        longitude: location.longitude,
        locationSource: location.source,
      );
      final local = result['local'] as Map<String, dynamic>? ?? {};
      await RegiaoBaseService.registrarObservacao(
        local: local,
        latitude: location.latitude,
        longitude: location.longitude,
      );
      if (!mounted) {
        return;
      }
      setState(() => lastResult = result);
      final jaConsiderado = result['status'] == 'ja_considerado';
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(jaConsiderado
              ? 'Envio recebido. Para proteger o mapa, repeticoes recentes entram como revisao e nao viram novo foco.'
              : 'Sintomas enviados com seguranca. Obrigado por contribuir.'),
          duration: const Duration(seconds: 5),
        ),
      );
    } catch (error) {
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
            content: Text(error.toString().replaceFirst('Exception: ', ''))),
      );
    } finally {
      if (mounted) {
        setState(() => loading = false);
      }
    }
  }

  Future<LocationSnapshot?> _resolverLocalizacaoEnvio() async {
    try {
      return await LocationService.getCurrentLocationForSubmission();
    } catch (error) {
      final base = await RegiaoBaseService.obterRegiaoBase();
      final fallback = await LocationService.getBestEffortLocation(
        fallbackRegion: base,
      );
      if (!mounted) {
        return null;
      }
      final usarAproximado = await showDialog<bool>(
            context: context,
            builder: (context) => AlertDialog(
              title: const Text('Localizacao atual indisponivel'),
              content: const Text(
                'Nao consegui confirmar o GPS agora. Voce pode tentar novamente com o GPS ativo ou enviar um sinal aproximado para revisao. Sinais aproximados ajudam o radar, mas recebem menor peso para evitar local errado.',
              ),
              actions: [
                TextButton(
                  onPressed: () => Navigator.pop(context, false),
                  child: const Text('Tentar depois'),
                ),
                FilledButton(
                  onPressed: () => Navigator.pop(context, true),
                  child: const Text('Enviar aproximado'),
                ),
              ],
            ),
          ) ??
          false;
      if (!usarAproximado) {
        rethrow;
      }
      return LocationSnapshot(
        latitude: fallback.latitude,
        longitude: fallback.longitude,
        source: fallback.source == 'current'
            ? 'current'
            : 'approximate_user_confirmed',
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Registrar sintomas')),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(18, 8, 18, 32),
        children: [
          Container(
            padding: const EdgeInsets.all(20),
            decoration: BoxDecoration(
              borderRadius: BorderRadius.circular(28),
              gradient: const LinearGradient(
                colors: [Color(0xFF182E44), Color(0xFF0A1824)],
              ),
            ),
            child: const Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  'Registrar sinais de saude',
                  style: TextStyle(
                    color: Colors.white,
                    fontSize: 24,
                    fontWeight: FontWeight.w800,
                  ),
                ),
                SizedBox(height: 10),
                Text(
                  'Seu envio e anonimo e ajuda a acompanhar sinais de saude na sua regiao. Para proteger o mapa publico, envios repetidos nao sao contados como novos casos.',
                  style: TextStyle(
                    color: Color(0xFF9CC4DB),
                    height: 1.45,
                  ),
                ),
              ],
            ),
          ),
          const SizedBox(height: 18),
          ..._symptomTiles(),
          const SizedBox(height: 18),
          FilledButton.icon(
            onPressed: loading ? null : enviarDados,
            icon: loading
                ? const SizedBox(
                    width: 18,
                    height: 18,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  )
                : const Icon(Icons.cloud_upload_outlined),
            label: Text(loading ? 'Enviando...' : 'Enviar agora'),
            style: FilledButton.styleFrom(
              minimumSize: const Size.fromHeight(56),
            ),
          ),
          const SizedBox(height: 12),
          const Text(
            'Este app nao substitui atendimento medico. Em caso de agravamento, procure atendimento profissional imediatamente.',
            style: TextStyle(
              color: Color(0xFF88AFC5),
              height: 1.45,
            ),
          ),
          if (lastResult != null) ...[
            const SizedBox(height: 18),
            _FeedbackCard(data: lastResult!),
          ],
        ],
      ),
    );
  }

  List<Widget> _symptomTiles() {
    final items = <MapEntry<String, String>>[
      const MapEntry('febre', 'Febre'),
      const MapEntry('tosse', 'Tosse'),
      const MapEntry('dor_corpo', 'Dor no corpo'),
      const MapEntry('cansaco', 'Cansaco'),
      const MapEntry('falta_ar', 'Falta de ar'),
    ];

    return items
        .map(
          (entry) => Card(
            child: CheckboxListTile(
              controlAffinity: ListTileControlAffinity.leading,
              value: sintomas[entry.key] ?? false,
              onChanged: (value) {
                setState(() => sintomas[entry.key] = value ?? false);
              },
              title: Text(
                entry.value,
                style: const TextStyle(color: Colors.white),
              ),
              subtitle: const Text(
                'Sinal enviado para o radar epidemiologico.',
                style: TextStyle(color: Color(0xFF8BB4CA)),
              ),
            ),
          ),
        )
        .toList();
  }
}

class _FeedbackCard extends StatelessWidget {
  const _FeedbackCard({required this.data});

  final Map<String, dynamic> data;

  @override
  Widget build(BuildContext context) {
    final local = data['local'] as Map<String, dynamic>? ?? {};
    final motivos = data['motivos_suspeita'] as List<dynamic>? ?? [];
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
                fontSize: 18,
                fontWeight: FontWeight.w700,
              ),
            ),
            const SizedBox(height: 10),
            Text(
              'Sinal monitorado: ${data['grupo'] ?? 'Monitoramento geral'}',
              style: const TextStyle(color: Color(0xFF9CC4DB)),
            ),
            const SizedBox(height: 4),
            Text(
              'Orientacao do radar: ${data['classificacao'] ?? 'Monitoramento regional'}',
              style: const TextStyle(color: Color(0xFF9CC4DB)),
            ),
            const SizedBox(height: 4),
            Text(
              'Qualidade do sinal: ${_qualidadeSinal(data)}',
              style: const TextStyle(color: Color(0xFF9CC4DB)),
            ),
            if (data['status'] == 'ja_considerado') ...[
              const SizedBox(height: 8),
              const Text(
                'Este envio nao abriu um novo caso porque o radar ja recebeu um sinal recente deste aparelho ou rede.',
                style: TextStyle(color: Color(0xFFFFD166), height: 1.35),
              ),
            ],
            const SizedBox(height: 4),
            Text(
              'Local identificado: ${local['bairro'] ?? 'Bairro'} / ${local['cidade'] ?? 'Cidade'} / ${local['estado'] ?? 'UF'}',
              style: const TextStyle(color: Color(0xFF9CC4DB)),
            ),
            if (motivos.isNotEmpty) ...[
              const SizedBox(height: 8),
              Text(
                'Observacao: o app usa verificacoes automaticas para proteger a qualidade do mapa publico.',
                style: const TextStyle(color: Color(0xFF88AFC5)),
              ),
            ],
          ],
        ),
      ),
    );
  }

  String _qualidadeSinal(Map<String, dynamic> data) {
    final valor = (data['confianca'] as num?)?.toDouble() ?? 0;
    if (valor >= 0.85) {
      return 'alta';
    }
    if (valor >= 0.6) {
      return 'moderada';
    }
    return 'em verificacao';
  }
}
