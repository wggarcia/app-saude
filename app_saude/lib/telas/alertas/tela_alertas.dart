import 'package:flutter/material.dart';

import '../../servicos/alerta_inbox_service.dart';
import '../../servicos/location_service.dart';
import '../../servicos/public_api_service.dart';
import '../../servicos/regiao_base_service.dart';

class TelaAlertas extends StatefulWidget {
  const TelaAlertas({super.key});

  @override
  State<TelaAlertas> createState() => _TelaAlertasState();
}

class _TelaAlertasState extends State<TelaAlertas> {
  List<Map<String, dynamic>> _alertas = const [];
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final base = await RegiaoBaseService.obterRegiaoBase();
    try {
      final location = await LocationService.getBestEffortLocation(
        fallbackRegion: base,
      );
      final radar = await PublicApiService.fetchRadarLocal(
        latitude: location.latitude,
        longitude: location.longitude,
      );
      final local = radar['local'] as Map<String, dynamic>? ?? {};
      final alertas = await PublicApiService.fetchAlertas(
        cidade: local['cidade']?.toString(),
        estado: local['estado']?.toString(),
        bairro: local['bairro']?.toString(),
      );
      await AlertaInboxService.syncAlerts(alertas);
    } catch (_) {}

    final inbox = await AlertaInboxService.loadInbox();
    if (!mounted) {
      return;
    }
    setState(() {
      _alertas = inbox;
      _loading = false;
    });
  }

  Future<void> _openAlert(Map<String, dynamic> alerta) async {
    await AlertaInboxService.markAsRead(alerta);
    if (!mounted) {
      return;
    }
    await showModalBottomSheet<void>(
      context: context,
      backgroundColor: const Color(0xFF071B2A),
      isScrollControlled: true,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(28)),
      ),
      builder: (context) => DraggableScrollableSheet(
        expand: false,
        initialChildSize: 0.78,
        minChildSize: 0.45,
        maxChildSize: 0.95,
        builder: (context, scrollController) {
          final recorte = [
            alerta['bairro']?.toString(),
            alerta['cidade']?.toString(),
            alerta['estado']?.toString(),
          ].where((item) => item != null && item.isNotEmpty).join(' / ');
          return ListView(
            controller: scrollController,
            padding: const EdgeInsets.fromLTRB(20, 18, 20, 28),
            children: [
              Center(
                child: Container(
                  width: 48,
                  height: 5,
                  decoration: BoxDecoration(
                    color: Colors.white24,
                    borderRadius: BorderRadius.circular(999),
                  ),
                ),
              ),
              const SizedBox(height: 18),
              _SeverityChip(
                  value: alerta['gravidade']?.toString() ?? 'moderada'),
              const SizedBox(height: 14),
              Text(
                alerta['titulo']?.toString() ?? 'Comunicado oficial',
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 28,
                  fontWeight: FontWeight.w900,
                  height: 1.05,
                ),
              ),
              const SizedBox(height: 14),
              if (recorte.isNotEmpty)
                _InfoLine(icon: Icons.place_outlined, text: recorte),
              _InfoLine(
                icon: Icons.account_balance_outlined,
                text: alerta['orgao']?.toString() ?? 'Governo SolusCRT',
              ),
              _InfoLine(
                icon: Icons.schedule_outlined,
                text: _formatDate(
                  alerta['criado_em']?.toString() ??
                      alerta['received_at']?.toString(),
                ),
              ),
              const SizedBox(height: 18),
              Container(
                padding: const EdgeInsets.all(18),
                decoration: BoxDecoration(
                  color: const Color(0xFF0C2436),
                  borderRadius: BorderRadius.circular(22),
                  border: Border.all(color: Colors.white10),
                ),
                child: Text(
                  alerta['mensagem']?.toString() ?? '',
                  style: const TextStyle(
                    color: Color(0xFFD3E4EF),
                    height: 1.55,
                    fontSize: 16,
                  ),
                ),
              ),
              const SizedBox(height: 18),
              const _EmergencyPanel(),
            ],
          );
        },
      ),
    );
    await _load();
  }

  @override
  Widget build(BuildContext context) {
    final unread = _alertas.where((item) => item['unread'] == true).length;
    return Scaffold(
      appBar: AppBar(
        title: const Text('Alertas'),
        actions: [
          if (_alertas.isNotEmpty)
            TextButton(
              onPressed: () async {
                await AlertaInboxService.markAllAsRead();
                await _load();
              },
              child: const Text('Marcar tudo'),
            ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: _load,
        child: ListView(
          padding: const EdgeInsets.fromLTRB(18, 8, 18, 28),
          children: [
            _AlertsHero(unread: unread, total: _alertas.length),
            const SizedBox(height: 16),
            const _EmergencyPanel(),
            const SizedBox(height: 16),
            if (_loading)
              const Card(
                child: Padding(
                  padding: EdgeInsets.all(24),
                  child: Center(child: CircularProgressIndicator()),
                ),
              )
            else if (_alertas.isEmpty)
              const Card(
                child: Padding(
                  padding: EdgeInsets.all(22),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        'Nenhum alerta salvo por enquanto',
                        style: TextStyle(
                          color: Colors.white,
                          fontSize: 18,
                          fontWeight: FontWeight.w800,
                        ),
                      ),
                      SizedBox(height: 8),
                      Text(
                        'Quando houver comunicados oficiais para sua regiao ou para o Brasil, eles aparecerao aqui mesmo se voce perder a notificacao.',
                        style: TextStyle(
                          color: Color(0xFF9CC4DB),
                          height: 1.45,
                        ),
                      ),
                    ],
                  ),
                ),
              )
            else
              ..._alertas.map(
                (alerta) => Padding(
                  padding: const EdgeInsets.only(bottom: 12),
                  child: _AlertListTile(
                    alerta: alerta,
                    onTap: () => _openAlert(alerta),
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }
}

class _AlertsHero extends StatelessWidget {
  const _AlertsHero({required this.unread, required this.total});

  final int unread;
  final int total;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(22),
      decoration: BoxDecoration(
        borderRadius: BorderRadius.circular(28),
        gradient: const LinearGradient(
          colors: [Color(0xFF112E43), Color(0xFF0B2132)],
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
              color: Colors.white.withValues(alpha: 0.08),
              borderRadius: BorderRadius.circular(999),
            ),
            child: const Text(
              'Central oficial da populacao',
              style: TextStyle(
                color: Color(0xFFBEE9FF),
                fontWeight: FontWeight.w700,
                fontSize: 12,
              ),
            ),
          ),
          const SizedBox(height: 16),
          const Text(
            'Veja alertas publicados pela operacao governamental e mantenha orientacoes importantes sempre ao alcance.',
            style: TextStyle(
              color: Colors.white,
              fontSize: 24,
              fontWeight: FontWeight.w800,
              height: 1.1,
            ),
          ),
          const SizedBox(height: 14),
          Wrap(
            spacing: 10,
            runSpacing: 10,
            children: [
              _HeroPill(label: 'Nao lidos', value: '$unread'),
              _HeroPill(label: 'Historico salvo', value: '$total'),
            ],
          ),
        ],
      ),
    );
  }
}

class _HeroPill extends StatelessWidget {
  const _HeroPill({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
      decoration: BoxDecoration(
        color: const Color(0xFF183B50),
        borderRadius: BorderRadius.circular(18),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label,
              style: const TextStyle(color: Color(0xFF8AB1C7), fontSize: 12)),
          const SizedBox(height: 4),
          Text(value,
              style: const TextStyle(
                  color: Colors.white, fontWeight: FontWeight.w800)),
        ],
      ),
    );
  }
}

class _AlertListTile extends StatelessWidget {
  const _AlertListTile({required this.alerta, required this.onTap});

  final Map<String, dynamic> alerta;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    final recorte = [
      alerta['bairro']?.toString(),
      alerta['cidade']?.toString(),
      alerta['estado']?.toString(),
    ].where((item) => item != null && item.isNotEmpty).join(' / ');
    final unread = alerta['unread'] == true;

    return Material(
      color: Colors.transparent,
      child: InkWell(
        borderRadius: BorderRadius.circular(24),
        onTap: onTap,
        child: Container(
          padding: const EdgeInsets.all(18),
          decoration: BoxDecoration(
            color: unread ? const Color(0xFF143247) : const Color(0xFF0B2333),
            borderRadius: BorderRadius.circular(24),
            border: Border.all(
              color: unread
                  ? const Color(0xFF39D0C3).withValues(alpha: 0.45)
                  : Colors.white10,
            ),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  _SeverityChip(
                      value: alerta['gravidade']?.toString() ?? 'moderada'),
                  const Spacer(),
                  if (unread)
                    Container(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 10, vertical: 5),
                      decoration: BoxDecoration(
                        color: const Color(0xFF39D0C3),
                        borderRadius: BorderRadius.circular(999),
                      ),
                      child: const Text(
                        'Novo',
                        style: TextStyle(
                          color: Color(0xFF052434),
                          fontWeight: FontWeight.w900,
                          fontSize: 11,
                        ),
                      ),
                    ),
                ],
              ),
              const SizedBox(height: 12),
              Text(
                alerta['titulo']?.toString() ?? 'Comunicado oficial',
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 18,
                  fontWeight: FontWeight.w800,
                ),
              ),
              const SizedBox(height: 8),
              Text(
                alerta['mensagem']?.toString() ?? '',
                maxLines: 3,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(
                  color: Color(0xFFB8D0DE),
                  height: 1.4,
                ),
              ),
              const SizedBox(height: 10),
              if (recorte.isNotEmpty)
                Text(
                  recorte,
                  style: const TextStyle(
                    color: Color(0xFFFFD166),
                    fontSize: 12,
                    fontWeight: FontWeight.w700,
                  ),
                ),
              const SizedBox(height: 6),
              Text(
                _formatDate(
                  alerta['criado_em']?.toString() ??
                      alerta['received_at']?.toString(),
                ),
                style: const TextStyle(
                  color: Color(0xFF8CAABC),
                  fontSize: 12,
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
}

class _SeverityChip extends StatelessWidget {
  const _SeverityChip({required this.value});

  final String value;

  @override
  Widget build(BuildContext context) {
    final normalized = value.toLowerCase();
    final (background, foreground, label) = switch (normalized) {
      'critica' || 'critico' => (
          const Color(0xFF5C1E22),
          const Color(0xFFFFB9B5),
          'Critico'
        ),
      'alta' || 'alto' => (
          const Color(0xFF5B3A12),
          const Color(0xFFFFD59B),
          'Alto'
        ),
      'moderada' || 'moderado' => (
          const Color(0xFF5A5310),
          const Color(0xFFFFF0A5),
          'Moderado'
        ),
      _ => (const Color(0xFF164D39), const Color(0xFFB7F4D4), 'Baixo'),
    };

    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 7),
      decoration: BoxDecoration(
        color: background,
        borderRadius: BorderRadius.circular(999),
      ),
      child: Text(
        label,
        style: TextStyle(
          color: foreground,
          fontWeight: FontWeight.w800,
          fontSize: 12,
        ),
      ),
    );
  }
}

class _EmergencyPanel extends StatelessWidget {
  const _EmergencyPanel();

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: const Color(0xFF271319),
        borderRadius: BorderRadius.circular(24),
        border:
            Border.all(color: const Color(0xFFFF6B6B).withValues(alpha: 0.25)),
      ),
      child: const Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(Icons.health_and_safety_outlined, color: Color(0xFFFF8E8E)),
              SizedBox(width: 10),
              Expanded(
                child: Text(
                  'Quando procurar atendimento imediatamente',
                  style: TextStyle(
                    color: Colors.white,
                    fontWeight: FontWeight.w800,
                    fontSize: 18,
                  ),
                ),
              ),
            ],
          ),
          SizedBox(height: 12),
          Text(
            'Procure atendimento profissional urgente se houver falta de ar intensa, dor no peito, confusao, desmaio, febre muito alta persistente, rigidez de nuca, sangramento importante ou piora rapida do estado geral.',
            style: TextStyle(color: Color(0xFFFFD6D6), height: 1.45),
          ),
          SizedBox(height: 12),
          Text(
            'Este app apoia monitoramento populacional. Ele nao faz diagnostico nem substitui medico, UPA, hospital, SAMU ou orientacao clinica.',
            style: TextStyle(color: Color(0xFFFFC2C2), height: 1.45),
          ),
        ],
      ),
    );
  }
}

class _InfoLine extends StatelessWidget {
  const _InfoLine({required this.icon, required this.text});

  final IconData icon;
  final String text;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(icon, size: 18, color: const Color(0xFF39D0C3)),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              text,
              style: const TextStyle(color: Color(0xFFAAC5D5), height: 1.35),
            ),
          ),
        ],
      ),
    );
  }
}

String _formatDate(String? raw) {
  if (raw == null || raw.isEmpty) {
    return 'Agora';
  }
  final parsed = DateTime.tryParse(raw)?.toLocal();
  if (parsed == null) {
    return raw;
  }
  final day = parsed.day.toString().padLeft(2, '0');
  final month = parsed.month.toString().padLeft(2, '0');
  final year = parsed.year.toString();
  final hour = parsed.hour.toString().padLeft(2, '0');
  final minute = parsed.minute.toString().padLeft(2, '0');
  return '$day/$month/$year $hour:$minute';
}
