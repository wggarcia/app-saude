import 'package:flutter/material.dart';

import '../../servicos/funcionario_auth_service.dart';
import 'navegador_funcionario.dart';

class TelaRegistroFuncionario extends StatefulWidget {
  const TelaRegistroFuncionario({super.key});

  @override
  State<TelaRegistroFuncionario> createState() => _TelaRegistroFuncionarioState();
}

class _TelaRegistroFuncionarioState extends State<TelaRegistroFuncionario> {
  final _cpf = TextEditingController();
  final _email = TextEditingController();
  final _senha = TextEditingController();
  final _confirma = TextEditingController();
  bool _loading = false;
  bool _senhaVisivel = false;
  String? _erro;

  @override
  void dispose() {
    _cpf.dispose();
    _email.dispose();
    _senha.dispose();
    _confirma.dispose();
    super.dispose();
  }

  Future<void> _registrar() async {
    final cpf = _cpf.text.trim();
    final email = _email.text.trim();
    final senha = _senha.text;
    final confirma = _confirma.text;

    if (cpf.isEmpty || email.isEmpty || senha.isEmpty) {
      setState(() => _erro = 'Preencha todos os campos.');
      return;
    }
    if (senha != confirma) {
      setState(() => _erro = 'As senhas não coincidem.');
      return;
    }
    if (senha.length < 6) {
      setState(() => _erro = 'Senha deve ter pelo menos 6 caracteres.');
      return;
    }

    setState(() { _loading = true; _erro = null; });

    try {
      final payload = await FuncionarioAuthService.registrar(cpf, email, senha);
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

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Criar conta')),
      body: SafeArea(
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 460),
            child: ListView(
              padding: const EdgeInsets.all(24),
              shrinkWrap: true,
              children: [
                const Icon(Icons.person_add_outlined, size: 56),
                const SizedBox(height: 16),
                Text(
                  'Crie sua conta',
                  textAlign: TextAlign.center,
                  style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                    fontWeight: FontWeight.w800,
                  ),
                ),
                const SizedBox(height: 6),
                Text(
                  'Use o CPF cadastrado pelo seu RH para vincular sua conta.',
                  textAlign: TextAlign.center,
                  style: Theme.of(context).textTheme.bodySmall?.copyWith(
                    color: Colors.white60,
                  ),
                ),
                const SizedBox(height: 24),
                TextField(
                  controller: _cpf,
                  keyboardType: TextInputType.number,
                  textInputAction: TextInputAction.next,
                  decoration: const InputDecoration(
                    labelText: 'CPF',
                    hintText: '000.000.000-00',
                    prefixIcon: Icon(Icons.badge_outlined),
                  ),
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: _email,
                  keyboardType: TextInputType.emailAddress,
                  textInputAction: TextInputAction.next,
                  decoration: const InputDecoration(
                    labelText: 'E-mail',
                    prefixIcon: Icon(Icons.email_outlined),
                  ),
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: _senha,
                  obscureText: !_senhaVisivel,
                  textInputAction: TextInputAction.next,
                  decoration: InputDecoration(
                    labelText: 'Senha',
                    prefixIcon: const Icon(Icons.lock_outline),
                    suffixIcon: IconButton(
                      icon: Icon(_senhaVisivel ? Icons.visibility_off : Icons.visibility),
                      onPressed: () => setState(() => _senhaVisivel = !_senhaVisivel),
                    ),
                  ),
                ),
                const SizedBox(height: 12),
                TextField(
                  controller: _confirma,
                  obscureText: !_senhaVisivel,
                  textInputAction: TextInputAction.done,
                  onSubmitted: (_) => _loading ? null : _registrar(),
                  decoration: const InputDecoration(
                    labelText: 'Confirmar senha',
                    prefixIcon: Icon(Icons.lock_outline),
                  ),
                ),
                const SizedBox(height: 16),
                if (_erro != null) _ErroCard(_erro!),
                const SizedBox(height: 16),
                FilledButton.icon(
                  onPressed: _loading ? null : _registrar,
                  icon: _loading
                      ? const SizedBox(width: 18, height: 18,
                          child: CircularProgressIndicator(strokeWidth: 2))
                      : const Icon(Icons.person_add),
                  label: Text(_loading ? 'Criando conta...' : 'Criar conta'),
                ),
                const SizedBox(height: 12),
                TextButton(
                  onPressed: () => Navigator.of(context).pop(),
                  child: const Text('Já tenho conta — fazer login'),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _ErroCard extends StatelessWidget {
  const _ErroCard(this.mensagem);
  final String mensagem;

  @override
  Widget build(BuildContext context) {
    return Card(
      color: Theme.of(context).colorScheme.error.withAlpha(36),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Row(
          children: [
            Icon(Icons.error_outline, color: Theme.of(context).colorScheme.error),
            const SizedBox(width: 10),
            Expanded(child: Text(mensagem)),
          ],
        ),
      ),
    );
  }
}
