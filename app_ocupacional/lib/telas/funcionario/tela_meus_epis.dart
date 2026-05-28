import 'dart:convert';
import 'dart:io';

import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';

import '../../servicos/funcionario_sst_service.dart';

class TelaMeusEpis extends StatefulWidget {
  const TelaMeusEpis({super.key});

  @override
  State<TelaMeusEpis> createState() => _TelaMeusEpisState();
}

class _TelaMeusEpisState extends State<TelaMeusEpis>
    with SingleTickerProviderStateMixin {
  late TabController _tabs;
  List<Map<String, dynamic>> _epis = [];
  List<Map<String, dynamic>> _pendentes = [];
  String? _erro;
  bool _loading = true;

  static const _teal = Color(0xFF27D3BE);
  static const _surface = Color(0xFF102A32);
  static const _amber = Color(0xFFFFB454);
  static const _red = Color(0xFFFF6B6B);

  @override
  void initState() {
    super.initState();
    _tabs = TabController(length: 2, vsync: this);
    _carregar();
  }

  @override
  void dispose() {
    _tabs.dispose();
    super.dispose();
  }

  Future<void> _carregar() async {
    setState(() {
      _loading = true;
      _erro = null;
    });
    try {
      final results = await Future.wait([
        FuncionarioSstService.epis(),
        FuncionarioSstService.episPendentesEntrega()
            .catchError((_) => <String, dynamic>{}),
      ]);
      if (!mounted) return;
      setState(() {
        _epis = List<Map<String, dynamic>>.from(
            (results[0]['epis'] as List? ?? []));
        _pendentes = List<Map<String, dynamic>>.from(
            (results[1]['pendentes'] as List? ?? []));
      });
    } catch (e) {
      if (!mounted) return;
      setState(() => _erro = e.toString().replaceFirst('Exception: ', ''));
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  // ── Determina cor/label do status ──────────────────────────────────────
  _EpiStatus _status(Map<String, dynamic> epi) {
    final raw = (epi['status'] ?? epi['status_display'] ?? '').toString().toLowerCase();
    final valStr = (epi['data_vencimento'] ?? epi['validade'] ?? '').toString();
    int dias = 999;
    if (valStr.isNotEmpty && valStr != 'null') {
      try {
        dias = DateTime.parse(valStr).difference(DateTime.now()).inDays;
      } catch (_) {}
    }
    if (raw.contains('venc') || raw.contains('expir') || dias < 0) {
      return _EpiStatus('Vencido', _red, Icons.warning_amber_outlined);
    }
    if (dias <= 30) {
      return _EpiStatus('A vencer', _amber, Icons.timer_outlined);
    }
    return _EpiStatus('Válido', _teal, Icons.check_circle_outline);
  }

  // ── Confirma entrega com câmera ────────────────────────────────────────
  Future<void> _confirmarEntrega(Map<String, dynamic> entrega) async {
    final picker = ImagePicker();
    final XFile? foto = await showDialog<XFile?>(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: _surface,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(18)),
        title: const Text('Confirmar entrega',
            style: TextStyle(color: Colors.white, fontWeight: FontWeight.w800)),
        content: Text(
          'Tire uma foto para confirmar o recebimento do EPI:\n'
          '${entrega['epi_nome'] ?? 'EPI'}',
          style: const TextStyle(color: Colors.white60, fontSize: 13),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx),
            child: const Text('Cancelar',
                style: TextStyle(color: Colors.white38)),
          ),
          FilledButton.icon(
            style: FilledButton.styleFrom(backgroundColor: _teal),
            onPressed: () async {
              Navigator.pop(ctx); // fecha dialog antes de abrir câmera
              final x = await picker.pickImage(
                source: ImageSource.camera,
                imageQuality: 60,
                maxWidth: 800,
              );
              if (ctx.mounted) Navigator.pop(ctx, x);
            },
            icon: const Icon(Icons.camera_alt_outlined, size: 18),
            label: const Text('Abrir câmera',
                style: TextStyle(fontWeight: FontWeight.w800)),
          ),
        ],
      ),
    );

    if (foto == null || !mounted) return;

    // Mostra loading
    showDialog(
      context: context,
      barrierDismissible: false,
      builder: (_) => const Center(child: CircularProgressIndicator()),
    );

    try {
      final bytes = await File(foto.path).readAsBytes();
      final base64Foto = base64Encode(bytes);
      final entregaId = entrega['id'] as int;
      final resp =
          await FuncionarioSstService.confirmarEpiComFoto(entregaId, base64Foto);
      if (!mounted) return;
      Navigator.pop(context); // fecha loading
      if (resp['ok'] == true) {
        _mostrarSnack('✅ Entrega confirmada com sucesso!', ok: true);
        _carregar();
      } else {
        _mostrarSnack(resp['erro'] ?? 'Erro ao confirmar entrega', ok: false);
      }
    } catch (e) {
      if (!mounted) return;
      Navigator.pop(context);
      _mostrarSnack('Erro de conexão. Tente novamente.', ok: false);
    }
  }

  void _mostrarSnack(String msg, {required bool ok}) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(msg),
        backgroundColor: ok ? _teal.withValues(alpha: 0.9) : _red.withValues(alpha: 0.9),
        behavior: SnackBarBehavior.floating,
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
      ),
    );
  }

  // ── Build ──────────────────────────────────────────────────────────────
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Meus EPIs'),
        actions: [
          IconButton(
              icon: const Icon(Icons.refresh),
              onPressed: _carregar,
              tooltip: 'Atualizar'),
        ],
        bottom: TabBar(
          controller: _tabs,
          indicatorColor: _teal,
          labelColor: _teal,
          unselectedLabelColor: Colors.white38,
          tabs: [
            const Tab(text: 'Equipamentos'),
            Tab(
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  const Text('Confirmar Entrega'),
                  if (_pendentes.isNotEmpty) ...[
                    const SizedBox(width: 6),
                    Container(
                      padding: const EdgeInsets.symmetric(
                          horizontal: 6, vertical: 2),
                      decoration: BoxDecoration(
                        color: _amber.withValues(alpha: 0.2),
                        borderRadius: BorderRadius.circular(999),
                        border: Border.all(
                            color: _amber.withValues(alpha: 0.6), width: 1),
                      ),
                      child: Text('${_pendentes.length}',
                          style: const TextStyle(
                              fontSize: 10, fontWeight: FontWeight.w800,
                              color: _amber)),
                    ),
                  ],
                ],
              ),
            ),
          ],
        ),
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _erro != null
              ? _ErroView(erro: _erro!, onRetry: _carregar)
              : TabBarView(
                  controller: _tabs,
                  children: [
                    _EpisTab(epis: _epis, statusFn: _status),
                    _PendentesTab(
                      pendentes: _pendentes,
                      onConfirmar: _confirmarEntrega,
                    ),
                  ],
                ),
    );
  }
}

// ── Tab: Lista de EPIs ────────────────────────────────────────────────────
class _EpisTab extends StatelessWidget {
  const _EpisTab({required this.epis, required this.statusFn});
  final List<Map<String, dynamic>> epis;
  final _EpiStatus Function(Map<String, dynamic>) statusFn;

  static const _surface = Color(0xFF102A32);

  @override
  Widget build(BuildContext context) {
    if (epis.isEmpty) {
      return const Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.security_outlined, size: 56, color: Colors.white24),
            SizedBox(height: 12),
            Text('Nenhum EPI atribuído.',
                style: TextStyle(color: Colors.white38, fontSize: 15)),
            SizedBox(height: 6),
            Text('Seus equipamentos de proteção aparecerão aqui.',
                style: TextStyle(color: Colors.white24, fontSize: 12)),
          ],
        ),
      );
    }

    // Separa por status para ordenar: vencidos > a vencer > válidos
    final sorted = List<Map<String, dynamic>>.from(epis);
    sorted.sort((a, b) {
      final pa = _priority(statusFn(a).label);
      final pb = _priority(statusFn(b).label);
      return pa.compareTo(pb);
    });

    return RefreshIndicator(
      onRefresh: () async {},
      child: ListView.separated(
        padding: const EdgeInsets.all(16),
        itemCount: sorted.length,
        separatorBuilder: (_, __) => const SizedBox(height: 10),
        itemBuilder: (ctx, i) {
          final epi = sorted[i];
          final st = statusFn(epi);
          final nome = (epi['nome'] ?? epi['equipamento'] ?? 'EPI').toString();
          final ca = (epi['ca'] ?? epi['certificado_aprovacao'] ?? '').toString();
          final validade =
              (epi['data_vencimento'] ?? epi['validade'] ?? '').toString();
          final entregue = epi['data_entrega']?.toString() ?? '';
          final qtd = epi['quantidade']?.toString() ?? '1';

          return Container(
            decoration: BoxDecoration(
              color: _surface,
              borderRadius: BorderRadius.circular(16),
              border: Border(
                  left: BorderSide(color: st.color, width: 4)),
            ),
            child: Padding(
              padding: const EdgeInsets.all(14),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(children: [
                    Expanded(
                      child: Text(nome,
                          style: const TextStyle(
                              color: Colors.white,
                              fontWeight: FontWeight.w700,
                              fontSize: 15)),
                    ),
                    _Badge(label: st.label, color: st.color, icon: st.icon),
                  ]),
                  const SizedBox(height: 10),
                  if (ca.isNotEmpty && ca != 'null')
                    _InfoRow(
                        icon: Icons.verified_outlined,
                        label: 'CA',
                        value: ca),
                  if (entregue.isNotEmpty && entregue != 'null') ...[
                    const SizedBox(height: 4),
                    _InfoRow(
                        icon: Icons.handshake_outlined,
                        label: 'Entregue',
                        value: entregue),
                  ],
                  if (validade.isNotEmpty && validade != 'null') ...[
                    const SizedBox(height: 4),
                    _InfoRow(
                        icon: Icons.event_outlined,
                        label: 'Vencimento',
                        value: validade,
                        valueColor: st.color),
                  ],
                  if (qtd != '1') ...[
                    const SizedBox(height: 4),
                    _InfoRow(
                        icon: Icons.numbers_outlined,
                        label: 'Qtd.',
                        value: qtd),
                  ],
                ],
              ),
            ),
          );
        },
      ),
    );
  }

  int _priority(String label) {
    if (label == 'Vencido') return 0;
    if (label == 'A vencer') return 1;
    return 2;
  }
}

// ── Tab: Pendentes de confirmação ─────────────────────────────────────────
class _PendentesTab extends StatelessWidget {
  const _PendentesTab(
      {required this.pendentes, required this.onConfirmar});
  final List<Map<String, dynamic>> pendentes;
  final Future<void> Function(Map<String, dynamic>) onConfirmar;

  static const _teal = Color(0xFF27D3BE);
  static const _amber = Color(0xFFFFB454);
  static const _surface = Color(0xFF102A32);

  @override
  Widget build(BuildContext context) {
    if (pendentes.isEmpty) {
      return const Center(
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(Icons.task_alt_outlined, size: 56, color: Color(0xFF27D3BE)),
            SizedBox(height: 12),
            Text('Tudo confirmado!',
                style: TextStyle(
                    color: Color(0xFF27D3BE),
                    fontSize: 16,
                    fontWeight: FontWeight.w700)),
            SizedBox(height: 6),
            Text('Nenhuma entrega pendente de confirmação.',
                style: TextStyle(color: Colors.white38, fontSize: 12)),
          ],
        ),
      );
    }

    return ListView(
      padding: const EdgeInsets.all(16),
      children: [
        Container(
          padding: const EdgeInsets.all(12),
          margin: const EdgeInsets.only(bottom: 16),
          decoration: BoxDecoration(
            color: _amber.withValues(alpha: 0.08),
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: _amber.withValues(alpha: 0.25)),
          ),
          child: const Row(
            children: [
              Icon(Icons.camera_alt_outlined, color: _amber, size: 18),
              SizedBox(width: 10),
              Expanded(
                child: Text(
                  'Confirme o recebimento tirando uma foto. '
                  'Isso registra legalmente a entrega do EPI.',
                  style: TextStyle(
                      color: _amber, fontSize: 12, height: 1.4),
                ),
              ),
            ],
          ),
        ),
        ...pendentes.map((e) {
          final nome = (e['epi_nome'] ?? 'EPI').toString();
          final data = (e['data_entrega'] ?? '').toString();
          final confirmada = e['biometria_confirmada'] == true;

          return Container(
            margin: const EdgeInsets.only(bottom: 10),
            decoration: BoxDecoration(
              color: _surface,
              borderRadius: BorderRadius.circular(16),
            ),
            child: ListTile(
              contentPadding:
                  const EdgeInsets.symmetric(horizontal: 16, vertical: 8),
              leading: Container(
                width: 44,
                height: 44,
                decoration: BoxDecoration(
                  color: _teal.withValues(alpha: 0.12),
                  borderRadius: BorderRadius.circular(10),
                ),
                child: const Icon(Icons.security_outlined,
                    color: _teal, size: 22),
              ),
              title: Text(nome,
                  style: const TextStyle(
                      color: Colors.white,
                      fontWeight: FontWeight.w700,
                      fontSize: 14)),
              subtitle: Text(
                data.isNotEmpty ? 'Entregue em: $data' : 'Aguardando confirmação',
                style: const TextStyle(color: Colors.white38, fontSize: 12),
              ),
              trailing: confirmada
                  ? const Icon(Icons.check_circle,
                      color: _teal, size: 26)
                  : FilledButton(
                      style: FilledButton.styleFrom(
                        backgroundColor: _teal,
                        padding: const EdgeInsets.symmetric(
                            horizontal: 12, vertical: 8),
                        shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(10)),
                      ),
                      onPressed: () => onConfirmar(e),
                      child: const Text('Confirmar',
                          style: TextStyle(
                              color: Color(0xFF041018),
                              fontWeight: FontWeight.w800,
                              fontSize: 12)),
                    ),
            ),
          );
        }),
      ],
    );
  }
}

// ── Widgets auxiliares ────────────────────────────────────────────────────
class _EpiStatus {
  const _EpiStatus(this.label, this.color, this.icon);
  final String label;
  final Color color;
  final IconData icon;
}

class _Badge extends StatelessWidget {
  const _Badge(
      {required this.label, required this.color, required this.icon});
  final String label;
  final Color color;
  final IconData icon;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 4),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.15),
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: color.withValues(alpha: 0.4)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, color: color, size: 13),
          const SizedBox(width: 4),
          Text(label,
              style: TextStyle(
                  color: color,
                  fontWeight: FontWeight.w800,
                  fontSize: 11)),
        ],
      ),
    );
  }
}

class _InfoRow extends StatelessWidget {
  const _InfoRow(
      {required this.icon,
      required this.label,
      required this.value,
      this.valueColor});
  final IconData icon;
  final String label;
  final String value;
  final Color? valueColor;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Icon(icon, size: 13, color: Colors.white30),
        const SizedBox(width: 6),
        SizedBox(
            width: 70,
            child: Text(label,
                style: const TextStyle(
                    color: Colors.white30, fontSize: 11))),
        Expanded(
          child: Text(value,
              style: TextStyle(
                  color: valueColor ?? Colors.white60,
                  fontWeight: FontWeight.w600,
                  fontSize: 12)),
        ),
      ],
    );
  }
}

class _ErroView extends StatelessWidget {
  const _ErroView({required this.erro, required this.onRetry});
  final String erro;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.cloud_off_outlined,
                size: 48, color: Colors.white38),
            const SizedBox(height: 12),
            Text(erro,
                textAlign: TextAlign.center,
                style: const TextStyle(color: Colors.white60)),
            const SizedBox(height: 16),
            FilledButton.icon(
              onPressed: onRetry,
              icon: const Icon(Icons.refresh),
              label: const Text('Tentar novamente'),
            ),
          ],
        ),
      ),
    );
  }
}
