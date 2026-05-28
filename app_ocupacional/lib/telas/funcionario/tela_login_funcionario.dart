import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

import '../../servicos/funcionario_auth_service.dart';
import 'navegador_funcionario.dart';
import 'tela_registro_funcionario.dart';

class TelaLoginFuncionario extends StatefulWidget {
  const TelaLoginFuncionario({super.key});

  @override
  State<TelaLoginFuncionario> createState() => _TelaLoginFuncionarioState();
}

class _TelaLoginFuncionarioState extends State<TelaLoginFuncionario> {
  final _email = TextEditingController();
  final _senha = TextEditingController();
  bool _loading = false;
  bool _senhaVisivel = false;
  String? _erro;

  @override
  void initState() {
    super.initState();
    _verificarSessao();
  }

  /// Se já existe token + dados salvos, vai direto para o dashboard.
  Future<void> _verificarSessao() async {
    final token = await FuncionarioAuthService.token();
    if (token == null || token.isEmpty) {
      // Sem sessão — apenas pré-preenche o e-mail
      final e = await FuncionarioAuthService.emailSalvo();
      if (e != null && e.isNotEmpty && mounted) _email.text = e;
      return;
    }
    final dados = await FuncionarioAuthService.dadosSalvos();
    final nome  = dados['nome'] ?? '';
    if (nome.isEmpty || !mounted) {
      final e = await FuncionarioAuthService.emailSalvo();
      if (e != null && e.isNotEmpty && mounted) _email.text = e;
      return;
    }
    // Sessão válida — navega diretamente para o dashboard
    if (!mounted) return;
    _irParaDashboard(nome, dados['cargo'] ?? '-', dados['empresa'] ?? '-');
  }

  void _irParaDashboard(String nome, String cargo, String empresa) {
    Navigator.of(context).pushReplacement(
      MaterialPageRoute(
        builder: (_) => NavegadorFuncionario(
          nome: nome,
          cargo: cargo,
          empresaNome: empresa,
        ),
      ),
    );
  }

  @override
  void dispose() {
    _email.dispose();
    _senha.dispose();
    super.dispose();
  }

  Future<void> _entrar() async {
    setState(() { _loading = true; _erro = null; });
    try {
      final payload = await FuncionarioAuthService.login(
        _email.text.trim(),
        _senha.text,
      );
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

  void _irParaRegistro() {
    Navigator.of(context).push(
      MaterialPageRoute(builder: (_) => const TelaRegistroFuncionario()),
    );
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
              padding: const EdgeInsets.all(24),
              shrinkWrap: true,
              children: [
                const Icon(Icons.badge_outlined, size: 56),
                const SizedBox(height: 16),
                Text(
                  'Portal do trabalhador',
                  textAlign: TextAlign.center,
                  style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                    fontWeight: FontWeight.w800,
                  ),
                ),
                const SizedBox(height: 6),
                Text(
                  'Entre com seu e-mail e senha cadastrados no app.',
                  textAlign: TextAlign.center,
                  style: Theme.of(context).textTheme.bodySmall?.copyWith(
                    color: Colors.white60,
                  ),
                ),
                const SizedBox(height: 28),
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
                  textInputAction: TextInputAction.done,
                  onSubmitted: (_) => _loading ? null : _entrar(),
                  decoration: InputDecoration(
                    labelText: 'Senha',
                    prefixIcon: const Icon(Icons.lock_outline),
                    suffixIcon: IconButton(
                      icon: Icon(_senhaVisivel ? Icons.visibility_off : Icons.visibility),
                      onPressed: () => setState(() => _senhaVisivel = !_senhaVisivel),
                    ),
                  ),
                ),
                const SizedBox(height: 16),
                if (_erro != null) _ErroLogin(_erro!),
                const SizedBox(height: 16),
                FilledButton.icon(
                  onPressed: _loading ? null : _entrar,
                  icon: _loading
                      ? const SizedBox(width: 18, height: 18,
                          child: CircularProgressIndicator(strokeWidth: 2))
                      : const Icon(Icons.login),
                  label: Text(_loading ? 'Entrando...' : 'Entrar'),
                ),
                const SizedBox(height: 20),
                const Divider(),
                const SizedBox(height: 12),
                OutlinedButton.icon(
                  onPressed: _irParaRegistro,
                  icon: const Icon(Icons.person_add_outlined),
                  label: const Text('Criar conta'),
                ),
                const SizedBox(height: 8),
                Text(
                  'Ainda não tem conta? Crie usando o CPF cadastrado pelo seu RH.',
                  textAlign: TextAlign.center,
                  style: Theme.of(context).textTheme.bodySmall?.copyWith(
                    color: Colors.white38,
                    fontSize: 11,
                  ),
                ),
                // ── Debug quick-login (apenas em debug mode) ────────────────
                if (kDebugMode) ...[
                  const SizedBox(height: 20),
                  const Divider(color: Colors.white12),
                  const SizedBox(height: 8),
                  TextButton.icon(
                    onPressed: _loading ? null : () async {
                      setState(() { _loading = true; _erro = null; });
                      try {
                        final payload = await FuncionarioAuthService.login(
                          'luiz@app.local', 'Luiz@2026');
                        if (!mounted) return;
                        _irParaDashboard(
                          payload['nome']?.toString() ?? 'Luiz Oliveira',
                          payload['cargo']?.toString() ?? '-',
                          payload['empresa_nome']?.toString() ?? '-',
                        );
                      } catch (e) {
                        if (mounted) setState(() {
                          _erro = e.toString().replaceFirst('Exception: ', '');
                          _loading = false;
                        });
                      }
                    },
                    icon: const Icon(Icons.developer_mode, size: 14),
                    label: const Text('DEBUG: Luiz Oliveira',
                        style: TextStyle(fontSize: 11)),
                    style: TextButton.styleFrom(foregroundColor: Colors.white24),
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
            Icon(Icons.error_outline, color: Theme.of(context).colorScheme.error),
            const SizedBox(width: 10),
            Expanded(child: Text(mensagem)),
          ],
        ),
      ),
    );
  }
}
