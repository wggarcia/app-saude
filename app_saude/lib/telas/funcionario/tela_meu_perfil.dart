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
  static const _bg = Color(0xFF04131F);
  static const _accent = Color(0xFF39D0C3);

  Map<String, dynamic>? _perfil;
  bool _loading = true;
  String? _erro;

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
      final data = await FuncionarioSSTService.getMeuPerfil();
      if (!mounted) return;
      setState(() {
        _perfil = data;
        _loading = false;
      });
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _erro = e.toString().replaceFirst('Exception: ', '');
        _loading = false;
      });
    }
  }

  Future<void> _logout() async {
    final confirmar = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        backgroundColor: const Color(0xFF0B2333),
        title: const Text('Sair', style: TextStyle(color: Colors.white)),
        content: const Text(
          'Deseja encerrar a sessao?',
          style: TextStyle(color: Color(0xFF9CC4DB)),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(ctx).pop(false),
            child: const Text('Cancelar'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(ctx).pop(true),
            style: FilledButton.styleFrom(
              backgroundColor: const Color(0xFFFF6B6B),
              foregroundColor: Colors.white,
            ),
            child: const Text('Sair'),
          ),
        ],
      ),
    );
    if (confirmar != true || !mounted) return;
    await FuncionarioAuthService.logout();
    if (!mounted) return;
    Navigator.of(context).pushReplacement(
      MaterialPageRoute(builder: (_) => const TelaLoginFuncionario()),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: _bg,
      body: RefreshIndicator(
        color: _accent,
        onRefresh: _carregar,
        child: CustomScrollView(
          slivers: [
            SliverPadding(
              padding: const EdgeInsets.fromLTRB(16, 16, 16, 28),
              sliver: SliverList(
                delegate: SliverChildListDelegate([
                  if (_loading)
                    const Center(
                      child: Padding(
                        padding: EdgeInsets.symmetric(vertical: 60),
                        child: CircularProgressIndicator(color: _accent),
                      ),
                    ),
                  if (_erro != null && !_loading)
                    _ErroCard(mensagem: _erro!, onRetry: _carregar),
                  if (!_loading && _erro == null && _perfil != null) ...[
                    _PerfilHeader(perfil: _perfil!),
                    const SizedBox(height: 16),
                    _SecaoCard(
                      titulo: 'Dados pessoais',
                      campos: [
                        _Campo('Nome', _perfil!['nome']),
                        _Campo('CPF', _perfil!['cpf']),
                        _Campo('Data de nascimento', _perfil!['data_nascimento']),
                        _Campo('Sexo', _perfil!['sexo']),
                      ],
                    ),
                    const SizedBox(height: 16),
                    _SecaoCard(
                      titulo: 'Dados profissionais',
                      campos: [
                        _Campo('Matricula', _perfil!['matricula']),
                        _Campo('Cargo', _perfil!['cargo']),
                        _Campo('Setor', _perfil!['setor']),
                        _Campo('Data de admissao', _perfil!['data_admissao']),
                        _Campo('Classe de risco', _perfil!['classe_risco']),
                        _Campo('Empresa', _perfil!['empresa_nome']),
                      ],
                    ),
                    const SizedBox(height: 24),
                    SizedBox(
                      height: 52,
                      child: FilledButton.icon(
                        onPressed: _logout,
                        icon: const Icon(Icons.logout),
                        label: const Text(
                          'Sair',
                          style: TextStyle(
                            fontSize: 16,
                            fontWeight: FontWeight.w700,
                          ),
                        ),
                        style: FilledButton.styleFrom(
                          backgroundColor: const Color(0xFFFF6B6B),
                          foregroundColor: Colors.white,
                          shape: RoundedRectangleBorder(
                            borderRadius: BorderRadius.circular(16),
                          ),
                        ),
                      ),
                    ),
                  ],
                ]),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _PerfilHeader extends StatelessWidget {
  const _PerfilHeader({required this.perfil});

  final Map<String, dynamic> perfil;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        gradient: const LinearGradient(
          colors: [Color(0xFF12324B), Color(0xFF0A1B29)],
          begin: Alignment.topLeft,
          end: Alignment.bottomRight,
        ),
        borderRadius: BorderRadius.circular(16),
      ),
      child: Row(
        children: [
          Container(
            width: 56,
            height: 56,
            decoration: BoxDecoration(
              color: const Color(0xFF39D0C3).withValues(alpha: 0.15),
              shape: BoxShape.circle,
              border: Border.all(
                color: const Color(0xFF39D0C3).withValues(alpha: 0.4),
              ),
            ),
            child: const Icon(
              Icons.person,
              color: Color(0xFF39D0C3),
              size: 30,
            ),
          ),
          const SizedBox(width: 16),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  perfil['nome']?.toString() ?? '-',
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 18,
                    fontWeight: FontWeight.w800,
                  ),
                ),
                const SizedBox(height: 4),
                Text(
                  perfil['cargo']?.toString() ?? '',
                  style: const TextStyle(
                    color: Color(0xFF39D0C3),
                    fontSize: 13,
                    fontWeight: FontWeight.w600,
                  ),
                ),
                Text(
                  perfil['empresa_nome']?.toString() ?? '',
                  style: TextStyle(
                    color: Colors.white.withValues(alpha: 0.55),
                    fontSize: 12,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _Campo {
  const _Campo(this.label, this.valor);

  final String label;
  final dynamic valor;
}

class _SecaoCard extends StatelessWidget {
  const _SecaoCard({required this.titulo, required this.campos});

  final String titulo;
  final List<_Campo> campos;

  @override
  Widget build(BuildContext context) {
    final camposFiltrados = campos.where((c) => c.valor != null).toList();
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0xFF0B2333),
        borderRadius: BorderRadius.circular(16),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            titulo,
            style: const TextStyle(
              color: Color(0xFF39D0C3),
              fontSize: 13,
              fontWeight: FontWeight.w700,
              letterSpacing: 0.5,
            ),
          ),
          const SizedBox(height: 12),
          ...camposFiltrados.map((c) => Padding(
                padding: const EdgeInsets.only(bottom: 10),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      c.label,
                      style: TextStyle(
                        color: Colors.white.withValues(alpha: 0.6),
                        fontSize: 12,
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(
                      c.valor.toString(),
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 15,
                        fontWeight: FontWeight.w500,
                      ),
                    ),
                  ],
                ),
              )),
        ],
      ),
    );
  }
}

class _ErroCard extends StatelessWidget {
  const _ErroCard({required this.mensagem, required this.onRetry});

  final String mensagem;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.symmetric(vertical: 20),
      padding: const EdgeInsets.all(20),
      decoration: BoxDecoration(
        color: const Color(0xFF4A1010),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
            color: const Color(0xFFFF6B6B).withValues(alpha: 0.4)),
      ),
      child: Column(
        children: [
          const Icon(Icons.error_outline, color: Color(0xFFFF6B6B), size: 32),
          const SizedBox(height: 8),
          Text(
            mensagem,
            textAlign: TextAlign.center,
            style: const TextStyle(color: Color(0xFFFF6B6B)),
          ),
          const SizedBox(height: 12),
          FilledButton(
            onPressed: onRetry,
            style: FilledButton.styleFrom(
              backgroundColor: const Color(0xFF39D0C3),
              foregroundColor: const Color(0xFF04131F),
            ),
            child: const Text('Tentar novamente'),
          ),
        ],
      ),
    );
  }
}
