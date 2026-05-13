import 'package:flutter/material.dart';

import '../../servicos/empresa_auth_service.dart';
import 'tela_dashboard_empresa.dart';

class TelaLoginEmpresa extends StatefulWidget {
  const TelaLoginEmpresa({super.key});

  @override
  State<TelaLoginEmpresa> createState() => _TelaLoginEmpresaState();
}

class _TelaLoginEmpresaState extends State<TelaLoginEmpresa> {
  final _email = TextEditingController();
  final _senha = TextEditingController();
  bool _loading = false;
  bool _podeForcarSessao = false;
  String? _erro;

  @override
  void dispose() {
    _email.dispose();
    _senha.dispose();
    super.dispose();
  }

  Future<void> _entrar({bool forceLogin = false}) async {
    setState(() {
      _loading = true;
      _erro = null;
      if (!forceLogin) _podeForcarSessao = false;
    });

    try {
      final session = await EmpresaAuthService.login(
        _email.text,
        _senha.text,
        forceLogin: forceLogin,
      );
      if (!mounted) return;
      Navigator.of(context).pushReplacement(
        MaterialPageRoute(
          builder: (_) =>
              TelaDashboardEmpresa(empresaNome: session.empresaNome),
        ),
      );
    } on SessaoEmUsoException catch (e) {
      if (!mounted) return;
      setState(() {
        _erro = e.message;
        _podeForcarSessao = true;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() => _erro = e.toString().replaceFirst('Exception: ', ''));
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Empresa')),
      body: SafeArea(
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 460),
            child: ListView(
              padding: const EdgeInsets.all(20),
              shrinkWrap: true,
              children: [
                const Icon(Icons.business_outlined, size: 56),
                const SizedBox(height: 18),
                Text(
                  'Acesso empresarial',
                  textAlign: TextAlign.center,
                  style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                    fontWeight: FontWeight.w800,
                  ),
                ),
                const SizedBox(height: 22),
                TextField(
                  controller: _email,
                  keyboardType: TextInputType.emailAddress,
                  textInputAction: TextInputAction.next,
                  autofillHints: const [AutofillHints.email],
                  decoration: const InputDecoration(
                    labelText: 'E-mail',
                    prefixIcon: Icon(Icons.mail_outline),
                  ),
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: _senha,
                  obscureText: true,
                  textInputAction: TextInputAction.done,
                  autofillHints: const [AutofillHints.password],
                  onSubmitted: (_) => _loading ? null : _entrar(),
                  decoration: const InputDecoration(
                    labelText: 'Senha',
                    prefixIcon: Icon(Icons.lock_outline),
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
                if (_podeForcarSessao) ...[
                  const SizedBox(height: 10),
                  OutlinedButton.icon(
                    onPressed: _loading
                        ? null
                        : () => _entrar(forceLogin: true),
                    icon: const Icon(Icons.devices_other_outlined),
                    label: const Text('Entrar neste dispositivo'),
                  ),
                ],
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
