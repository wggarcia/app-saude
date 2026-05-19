import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;

import '../../config.dart';
import '../../servicos/empresa_auth_service.dart';

class TelaFuncionariosEmpresa extends StatefulWidget {
  const TelaFuncionariosEmpresa({super.key});

  @override
  State<TelaFuncionariosEmpresa> createState() => _TelaFuncionariosEmpresaState();
}

class _TelaFuncionariosEmpresaState extends State<TelaFuncionariosEmpresa> {
  List<Map<String, dynamic>> _funcionarios = [];
  List<Map<String, dynamic>> _filtrados = [];
  bool _loading = true;
  String? _erro;
  final _busca = TextEditingController();

  @override
  void initState() {
    super.initState();
    _carregar();
    _busca.addListener(_filtrar);
  }

  @override
  void dispose() {
    _busca.dispose();
    super.dispose();
  }

  Future<void> _carregar() async {
    setState(() { _loading = true; _erro = null; });
    try {
      final token = await EmpresaAuthService.token();
      final r = await http.get(
        Uri.parse('${Config.baseUrl}/api/sst/funcionarios?limit=500'),
        headers: {'Authorization': 'Bearer $token'},
      );
      if (r.statusCode == 200) {
        final data = jsonDecode(r.body) as Map<String, dynamic>;
        final lista = List<Map<String, dynamic>>.from(data['funcionarios'] ?? []);
        setState(() { _funcionarios = lista; _filtrados = lista; });
      } else {
        throw Exception('Erro ${r.statusCode}');
      }
    } catch (e) {
      setState(() => _erro = e.toString().replaceFirst('Exception: ', ''));
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  void _filtrar() {
    final q = _busca.text.toLowerCase().trim();
    setState(() {
      _filtrados = q.isEmpty
          ? _funcionarios
          : _funcionarios.where((f) =>
              (f['nome'] as String).toLowerCase().contains(q) ||
              (f['cargo'] as String? ?? '').toLowerCase().contains(q) ||
              (f['setor'] as String? ?? '').toLowerCase().contains(q),
            ).toList();
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text('Equipe (${_filtrados.length})'),
        automaticallyImplyLeading: false,
        actions: [
          IconButton(icon: const Icon(Icons.refresh), onPressed: _carregar),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _erro != null
              ? Center(child: Text(_erro!, style: const TextStyle(color: Colors.redAccent)))
              : Column(
                  children: [
                    Padding(
                      padding: const EdgeInsets.all(12),
                      child: TextField(
                        controller: _busca,
                        decoration: const InputDecoration(
                          hintText: 'Buscar por nome, cargo ou setor...',
                          prefixIcon: Icon(Icons.search),
                          contentPadding: EdgeInsets.symmetric(horizontal: 16, vertical: 10),
                        ),
                      ),
                    ),
                    Expanded(
                      child: RefreshIndicator(
                        onRefresh: _carregar,
                        child: _filtrados.isEmpty
                            ? const Center(
                                child: Text('Nenhum funcionário encontrado.',
                                    style: TextStyle(color: Colors.white54)))
                            : ListView.separated(
                                padding: const EdgeInsets.symmetric(horizontal: 12),
                                itemCount: _filtrados.length,
                                separatorBuilder: (_, __) => const SizedBox(height: 6),
                                itemBuilder: (context, i) {
                                  final f = _filtrados[i];
                                  final ativo = f['ativo'] as bool? ?? true;
                                  return Card(
                                    child: ListTile(
                                      leading: CircleAvatar(
                                        backgroundColor: const Color(0xFF27D3BE).withOpacity(0.15),
                                        child: Text(
                                          (f['nome'] as String).isNotEmpty
                                              ? (f['nome'] as String)[0].toUpperCase()
                                              : '?',
                                          style: const TextStyle(
                                              color: Color(0xFF27D3BE), fontWeight: FontWeight.w800),
                                        ),
                                      ),
                                      title: Text(f['nome'] as String,
                                          style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 14)),
                                      subtitle: Text(
                                        '${f['cargo'] ?? ''}${(f['setor'] as String? ?? '').isNotEmpty ? ' · ${f['setor']}' : ''}',
                                        style: const TextStyle(fontSize: 12, color: Colors.white54),
                                      ),
                                      trailing: ativo
                                          ? null
                                          : Container(
                                              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                                              decoration: BoxDecoration(
                                                color: Colors.redAccent.withOpacity(0.15),
                                                borderRadius: BorderRadius.circular(99),
                                              ),
                                              child: const Text('Inativo',
                                                  style: TextStyle(fontSize: 11, color: Colors.redAccent)),
                                            ),
                                    ),
                                  );
                                },
                              ),
                      ),
                    ),
                  ],
                ),
    );
  }
}
