import 'package:flutter/material.dart';

import '../../servicos/funcionario_auth_service.dart';
import '../../servicos/funcionario_sst_service.dart';
import 'tela_login_funcionario.dart';

class TelaMeuPerfil extends StatefulWidget {
  const TelaMeuPerfil({super.key});

  @override
  State<TelaMeuPerfil> createState() => _TelaMeuPerfilState();
}

class _TelaMeuPerfilState extends State<TelaMeuPerfil> {
  Map<String, dynamic>? _perfil;
  String? _erro;
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _carregar();
  }

  Future<void> _carregar() async {
    setState(() {
      _loading = true;
      _erro = null;
    });
    try {
      final data = await FuncionarioSstService.perfil();
      if (!mounted) return;
      setState(() => _perfil = data);
    } catch (e) {
      if (!mounted) return;
      setState(() => _erro = e.toString().replaceFirst('Exception: ', ''));
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _logout() async {
    await FuncionarioAuthService.logout();
    if (!mounted) return;
    Navigator.of(context).pushReplacement(
      MaterialPageRoute(builder: (_) => const TelaLoginFuncionario()),
    );
  }

  @override
  Widget build(BuildContext context) {
    if (_loading) return const Center(child: CircularProgressIndicator());
    if (_erro != null) return _ErroState(mensagem: _erro!, onRetry: _carregar);

    final p = _perfil ?? {};
    return RefreshIndicator(
      onRefresh: _carregar,
      child: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          _Bloco('Dados pessoais', {
            'Nome': p['nome'],
            'CPF': p['cpf'],
            'Nascimento': p['data_nascimento'],
          }),
          const SizedBox(height: 12),
          _Bloco('Dados profissionais', {
            'Empresa': p['empresa_nome'],
            'Cargo': p['cargo'],
            'Matrícula': p['matricula'],
            'Setor': p['setor'],
          }),
          const SizedBox(height: 16),
          FilledButton.icon(
            onPressed: _logout,
            icon: const Icon(Icons.logout),
            label: const Text('Sair da sessão'),
          ),
        ],
      ),
    );
  }
}

class _Bloco extends StatelessWidget {
  const _Bloco(this.titulo, this.campos);
  final String titulo;
  final Map<String, dynamic> campos;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(titulo, style: const TextStyle(fontWeight: FontWeight.bold)),
            const SizedBox(height: 8),
            ...campos.entries.map(
              (e) => Padding(
                padding: const EdgeInsets.only(bottom: 6),
                child: Row(
                  children: [
                    SizedBox(width: 100, child: Text(e.key)),
                    Expanded(child: Text((e.value ?? '-').toString())),
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _ErroState extends StatelessWidget {
  const _ErroState({required this.mensagem, required this.onRetry});
  final String mensagem;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          Text(mensagem, textAlign: TextAlign.center),
          const SizedBox(height: 8),
          OutlinedButton(
            onPressed: onRetry,
            child: const Text('Tentar novamente'),
          ),
        ],
      ),
    );
  }
}
