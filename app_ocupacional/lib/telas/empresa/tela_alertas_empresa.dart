import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;

import '../../config.dart';
import '../../servicos/empresa_auth_service.dart';

class TelaAlertasEmpresa extends StatefulWidget {
  const TelaAlertasEmpresa({super.key});

  @override
  State<TelaAlertasEmpresa> createState() => _TelaAlertasEmpresaState();
}

class _TelaAlertasEmpresaState extends State<TelaAlertasEmpresa> {
  Map<String, dynamic>? _dados;
  bool _loading = true;
  String? _erro;

  @override
  void initState() {
    super.initState();
    _carregar();
  }

  Future<void> _carregar() async {
    setState(() { _loading = true; _erro = null; });
    try {
      final token = await EmpresaAuthService.token();
      final r = await http.get(
        Uri.parse('${Config.baseUrl}/api/sst/dashboard'),
        headers: {'Authorization': 'Bearer $token'},
      );
      if (r.statusCode == 200) {
        setState(() => _dados = jsonDecode(r.body) as Map<String, dynamic>);
      } else {
        throw Exception('Erro ${r.statusCode}');
      }
    } catch (e) {
      setState(() => _erro = e.toString().replaceFirst('Exception: ', ''));
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Alertas SST'),
        automaticallyImplyLeading: false,
        actions: [
          IconButton(icon: const Icon(Icons.refresh), onPressed: _carregar),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _erro != null
              ? Center(child: Text(_erro!, style: const TextStyle(color: Colors.redAccent)))
              : _buildConteudo(),
    );
  }

  Widget _buildConteudo() {
    final d = _dados ?? {};
    final alertas = d['alertas'] is List ? d['alertas'] as List : [];
    final asos = _map(d['asos']);
    final exames = _map(d['exames']);
    final afastamentos = _map(d['afastamentos']);

    return RefreshIndicator(
      onRefresh: _carregar,
      child: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          // ── KPIs críticos ─────────────────────────────────────────
          GridView.count(
            crossAxisCount: 2,
            mainAxisSpacing: 10,
            crossAxisSpacing: 10,
            childAspectRatio: 1.35,
            shrinkWrap: true,
            physics: const NeverScrollableScrollPhysics(),
            children: [
              _KpiAlerta('ASOs vencidos', asos['vencidos'], Icons.assignment_late_outlined, Colors.redAccent),
              _KpiAlerta('ASOs 60 dias', asos['a_vencer_60d'], Icons.event_outlined, Colors.orange),
              _KpiAlerta('Exames atrasados', exames['atrasados'], Icons.science_outlined, Colors.orange),
              _KpiAlerta('Absenteísmo', '${afastamentos['absenteismo_pct'] ?? 0}%', Icons.timeline_outlined, Colors.blueAccent),
            ],
          ),
          const SizedBox(height: 20),

          Text('Alertas ativos', style: Theme.of(context).textTheme.titleMedium?.copyWith(fontWeight: FontWeight.w800)),
          const SizedBox(height: 10),

          if (alertas.isEmpty)
            Card(
              child: Padding(
                padding: const EdgeInsets.all(24),
                child: Column(
                  children: [
                    const Icon(Icons.check_circle_outline, size: 48, color: Color(0xFF00C896)),
                    const SizedBox(height: 12),
                    Text('Nenhum alerta crítico no momento',
                        textAlign: TextAlign.center,
                        style: Theme.of(context).textTheme.bodyMedium?.copyWith(color: Colors.white54)),
                  ],
                ),
              ),
            )
          else
            ...alertas.map((alerta) {
              final item = alerta is Map ? alerta as Map<String, dynamic> : <String, dynamic>{};
              final nivel = item['nivel']?.toString() ?? '';
              final cor = nivel == 'critico'
                  ? Colors.redAccent
                  : nivel == 'alto'
                      ? Colors.orange
                      : Colors.blueAccent;
              return Card(
                margin: const EdgeInsets.only(bottom: 8),
                child: ListTile(
                  leading: Icon(Icons.warning_amber_outlined, color: cor),
                  title: Text(item['mensagem']?.toString() ?? 'Alerta',
                      style: const TextStyle(fontSize: 14, fontWeight: FontWeight.w600)),
                  subtitle: Text(nivel.toUpperCase(),
                      style: TextStyle(color: cor, fontSize: 11, fontWeight: FontWeight.w800)),
                ),
              );
            }),
        ],
      ),
    );
  }

  static Map<String, dynamic> _map(Object? v) =>
      v is Map<String, dynamic> ? v : {};
}

class _KpiAlerta extends StatelessWidget {
  const _KpiAlerta(this.label, this.valor, this.icon, this.cor);
  final String label;
  final Object? valor;
  final IconData icon;
  final Color cor;

  @override
  Widget build(BuildContext context) {
    final v = valor?.toString() ?? '0';
    final zero = v == '0' || v == '0%';
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Icon(icon, color: zero ? Colors.white24 : cor),
            Text(v,
                style: TextStyle(
                  fontSize: 26,
                  fontWeight: FontWeight.w900,
                  color: zero ? Colors.white24 : cor,
                )),
            Text(label, style: const TextStyle(fontSize: 11, color: Colors.white54), maxLines: 2, overflow: TextOverflow.ellipsis),
          ],
        ),
      ),
    );
  }
}
