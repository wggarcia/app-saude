import 'package:flutter/material.dart';

import '../../servicos/funcionario_auth_service.dart';
import 'navegador_funcionario.dart';

class TelaLoginFuncionario extends StatefulWidget {
  const TelaLoginFuncionario({super.key});

  @override
  State<TelaLoginFuncionario> createState() => _TelaLoginFuncionarioState();
}

class _TelaLoginFuncionarioState extends State<TelaLoginFuncionario> {
  final _cpf = TextEditingController();
  final _data = TextEditingController();
  bool _loading = false;
  String? _erro;

  @override
  void dispose() {
    _cpf.dispose();
    _data.dispose();
    super.dispose();
  }

  Future<void> _entrar() async {
    setState(() {
      _loading = true;
      _erro = null;
    });

    try {
      final iso = _dataNascimentoIso(_data.text);
      final payload = await FuncionarioAuthService.login(_cpf.text, iso);
      if (!mounted) return;
      Navigator.of(context).pushReplacement(
        MaterialPageRoute(
          builder: (_) => NavegadorFuncionario(
            nome: payload['nome']?.toString() ?? 'Trabalhador',
            cargo: payload['cargo']?.toString() ?? '-',
            empresaNome: payload['empresa_nome']?.toString() ?? '-',
          ),
        ),
      );
    } catch (e) {
      if (!mounted) return;
      setState(() => _erro = e.toString().replaceFirst('Exception: ', ''));
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  String _dataNascimentoIso(String value) {
    final parts = value.trim().split('/');
    if (parts.length != 3) throw Exception('Data inválida. Use DD/MM/AAAA.');
    final dia = parts[0].padLeft(2, '0');
    final mes = parts[1].padLeft(2, '0');
    final ano = parts[2];
    if (dia.length != 2 || mes.length != 2 || ano.length != 4) {
      throw Exception('Data inválida. Use DD/MM/AAAA.');
    }
    return '$ano-$mes-$dia';
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Trabalhador')),
      body: SafeArea(
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 460),
            child: ListView(
              padding: const EdgeInsets.all(20),
              shrinkWrap: true,
              children: [
                const Icon(Icons.badge_outlined, size: 56),
                const SizedBox(height: 18),
                Text(
                  'Portal do trabalhador',
                  textAlign: TextAlign.center,
                  style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                        fontWeight: FontWeight.w800,
                      ),
                ),
                const SizedBox(height: 22),
                TextField(
                  controller: _cpf,
                  keyboardType: TextInputType.number,
                  textInputAction: TextInputAction.next,
                  decoration: const InputDecoration(
                    labelText: 'CPF',
                    prefixIcon: Icon(Icons.perm_identity_outlined),
                  ),
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: _data,
                  keyboardType: TextInputType.datetime,
                  textInputAction: TextInputAction.done,
                  onSubmitted: (_) => _loading ? null : _entrar(),
                  decoration: const InputDecoration(
                    labelText: 'Data de nascimento',
                    hintText: 'DD/MM/AAAA',
                    prefixIcon: Icon(Icons.calendar_today_outlined),
                  ),
                ),
                const SizedBox(height: 14),
                if (_erro != null) _ErroLogin(_erro!),
                const SizedBox(height: 14),
                FilledButton.icon(
                  onPressed: _loading ? null : _entrar,
                  icon: _loading
                      ? const SizedBox(
                          width: 18,
                          height: 18,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Icon(Icons.login),
                  label: Text(_loading ? 'Entrando...' : 'Entrar'),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _ErroLogin extends StatelessWidget {
  const _ErroLogin(this.mensagem);
  final String mensagem;

  @override
  Widget build(BuildContext context) {
    return Card(
      color: Theme.of(context).colorScheme.error.withAlpha(36),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Row(
          children: [
            Icon(
              Icons.error_outline,
              color: Theme.of(context).colorScheme.error,
            ),
            const SizedBox(width: 10),
            Expanded(child: Text(mensagem)),
          ],
        ),
      ),
    );
  }
}
