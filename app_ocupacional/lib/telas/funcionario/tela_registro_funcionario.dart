import 'package:flutter/material.dart';

import '../../servicos/funcionario_auth_service.dart';
import 'navegador_funcionario.dart';

class TelaRegistroFuncionario extends StatefulWidget {
  const TelaRegistroFuncionario({super.key});

  @override
  State<TelaRegistroFuncionario> createState() => _TelaRegistroFuncionarioState();
}

class _TelaRegistroFuncionarioState extends State<TelaRegistroFuncionario> {
  // Etapa 1: CPF
  final _cpf = TextEditingController();
  // Etapa 2: dados da conta
  final _email = TextEditingController();
  final _senha = TextEditingController();
  final _confirma = TextEditingController();

  bool _loading = false;
  bool _senhaVisivel = false;
  String? _erro;

  // Estado da etapa
  // null = etapa 1 (CPF)
  // lista preenchida = escolha de empresa
  // funcionario_id preenchido = etapa 2 (email+senha)
  List<Map<String, dynamic>>? _opcoes;
  int? _funcionarioId;
  // Prova do CPF validado na etapa 1 — enviada na etapa 2 no lugar do id cru.
  String? _registroToken;
  String? _nomeFunc;
  String? _empresaNomeEscolhida;

  @override
  void dispose() {
    _cpf.dispose();
    _email.dispose();
    _senha.dispose();
    _confirma.dispose();
    super.dispose();
  }

  // ── Etapa 1: busca CPF ────────────────────────────────────────────────────
  Future<void> _buscarCpf() async {
    final cpf = _cpf.text.trim();
    if (cpf.isEmpty) {
      setState(() => _erro = 'Digite seu CPF.');
      return;
    }
    setState(() { _loading = true; _erro = null; });
    try {
      final res = await FuncionarioAuthService.buscarCpf(cpf);
      if (!mounted) return;
      final status = res['status'] as String;
      if (status == 'ok') {
        // Única empresa — avança direto para etapa 2
        setState(() {
          _funcionarioId = res['funcionario_id'] as int;
          _registroToken = res['registro_token']?.toString();
          _nomeFunc = res['nome']?.toString();
          _empresaNomeEscolhida = res['empresa_nome']?.toString();
          _opcoes = null;
        });
      } else if (status == 'escolher_empresa') {
        // Múltiplas empresas — mostra seleção
        setState(() {
          _nomeFunc = res['nome']?.toString();
          _opcoes = List<Map<String, dynamic>>.from(res['opcoes'] as List);
          _funcionarioId = null;
        });
      }
    } catch (e) {
      if (!mounted) return;
      setState(() => _erro = e.toString().replaceFirst('Exception: ', ''));
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  // ── Seleciona empresa da lista ────────────────────────────────────────────
  void _selecionarEmpresa(Map<String, dynamic> opcao) {
    setState(() {
      _funcionarioId = opcao['funcionario_id'] as int;
      _registroToken = opcao['registro_token']?.toString();
      _empresaNomeEscolhida = opcao['empresa_nome']?.toString();
      _opcoes = null;
    });
  }

  // ── Etapa 2: cria a conta ─────────────────────────────────────────────────
  Future<void> _registrar() async {
    final email = _email.text.trim();
    final senha = _senha.text;
    final confirma = _confirma.text;

    if (email.isEmpty || senha.isEmpty) {
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

    if (_registroToken == null || _registroToken!.isEmpty) {
      setState(() => _erro = 'Sessão de registro expirada. Refaça a busca por CPF.');
      return;
    }

    setState(() { _loading = true; _erro = null; });
    try {
      final payload = await FuncionarioAuthService.registrar(
        _registroToken!,
        email,
        senha,
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

  void _voltarEtapa1() {
    setState(() {
      _funcionarioId = null;
      _registroToken = null;
      _opcoes = null;
      _nomeFunc = null;
      _empresaNomeEscolhida = null;
      _erro = null;
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Criar conta'),
        leading: (_funcionarioId != null || _opcoes != null)
            ? IconButton(
                icon: const Icon(Icons.arrow_back),
                onPressed: _voltarEtapa1,
              )
            : null,
      ),
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
                  'Use o CPF cadastrado pelo seu RH.',
                  textAlign: TextAlign.center,
                  style: Theme.of(context).textTheme.bodySmall?.copyWith(
                    color: Colors.white60,
                  ),
                ),
                const SizedBox(height: 24),

                // ── Etapa 1: CPF ──
                if (_funcionarioId == null && _opcoes == null) ...[
                  TextField(
                    controller: _cpf,
                    keyboardType: TextInputType.number,
                    textInputAction: TextInputAction.done,
                    onSubmitted: (_) => _loading ? null : _buscarCpf(),
                    decoration: const InputDecoration(
                      labelText: 'CPF',
                      hintText: '000.000.000-00',
                      prefixIcon: Icon(Icons.badge_outlined),
                    ),
                  ),
                  const SizedBox(height: 16),
                  if (_erro != null) _ErroCard(_erro!),
                  const SizedBox(height: 16),
                  FilledButton.icon(
                    onPressed: _loading ? null : _buscarCpf,
                    icon: _loading
                        ? const SizedBox(width: 18, height: 18,
                            child: CircularProgressIndicator(strokeWidth: 2))
                        : const Icon(Icons.search),
                    label: Text(_loading ? 'Buscando...' : 'Buscar CPF'),
                  ),
                ],

                // ── Etapa 1b: escolha de empresa ──
                if (_opcoes != null) ...[
                  Text(
                    'Olá, $_nomeFunc! Selecione sua empresa:',
                    style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 15),
                  ),
                  const SizedBox(height: 12),
                  ..._opcoes!.map((op) => Card(
                    margin: const EdgeInsets.only(bottom: 10),
                    child: InkWell(
                      borderRadius: BorderRadius.circular(16),
                      onTap: () => _selecionarEmpresa(op),
                      child: Padding(
                        padding: const EdgeInsets.all(16),
                        child: Row(
                          children: [
                            const Icon(Icons.business_outlined, size: 28),
                            const SizedBox(width: 14),
                            Expanded(
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Text(op['empresa_nome']?.toString() ?? '',
                                    style: const TextStyle(fontWeight: FontWeight.bold)),
                                  if ((op['cargo'] ?? '').toString().isNotEmpty)
                                    Text(op['cargo'].toString(),
                                      style: const TextStyle(fontSize: 12, color: Colors.white60)),
                                ],
                              ),
                            ),
                            const Icon(Icons.chevron_right),
                          ],
                        ),
                      ),
                    ),
                  )),
                ],

                // ── Etapa 2: email + senha ──
                if (_funcionarioId != null) ...[
                  Card(
                    color: Theme.of(context).colorScheme.primaryContainer.withAlpha(60),
                    child: Padding(
                      padding: const EdgeInsets.all(12),
                      child: Row(
                        children: [
                          const Icon(Icons.check_circle_outline,
                            color: Colors.tealAccent, size: 20),
                          const SizedBox(width: 10),
                          Expanded(
                            child: Text(
                              '${_nomeFunc ?? ''} — ${_empresaNomeEscolhida ?? ''}',
                              style: const TextStyle(fontWeight: FontWeight.w600),
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                  const SizedBox(height: 16),
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
                        icon: Icon(_senhaVisivel
                            ? Icons.visibility_off
                            : Icons.visibility),
                        onPressed: () =>
                            setState(() => _senhaVisivel = !_senhaVisivel),
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
                ],

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
