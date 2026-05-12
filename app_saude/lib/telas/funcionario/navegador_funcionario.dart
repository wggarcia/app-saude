import 'package:flutter/material.dart';
import '../../servicos/funcionario_auth_service.dart';
import 'tela_dashboard_funcionario.dart';
import 'tela_meus_asos.dart';
import 'tela_meus_treinamentos.dart';
import 'tela_meu_perfil.dart';
import 'tela_login_funcionario.dart';

class NavegadorFuncionario extends StatefulWidget {
  const NavegadorFuncionario({
    super.key,
    required this.nome,
    required this.cargo,
    required this.empresaNome,
  });

  final String nome;
  final String cargo;
  final String empresaNome;

  @override
  State<NavegadorFuncionario> createState() => _NavegadorFuncionarioState();
}

class _NavegadorFuncionarioState extends State<NavegadorFuncionario> {
  int _abaAtual = 0;

  List<Widget> get _pages => [
        TelaDashboardFuncionario(
          nomeInicial: widget.nome,
          cargoInicial: widget.cargo,
          empresaNomeInicial: widget.empresaNome,
        ),
        const TelaMeusAsos(),
        const TelaMeusTreinamentos(),
        const TelaMeuPerfil(),
      ];

  Future<void> _confirmarLogout() async {
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

  String get _tituloAba {
    return switch (_abaAtual) {
      0 => 'Inicio',
      1 => 'Meu ASO',
      2 => 'Treinamentos',
      3 => 'Meu Perfil',
      _ => '',
    };
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        backgroundColor: const Color(0xFF04131F),
        title: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              widget.nome.isNotEmpty ? widget.nome : 'Portal do Trabalhador',
              style: const TextStyle(
                color: Colors.white,
                fontSize: 16,
                fontWeight: FontWeight.w700,
              ),
            ),
            if (_tituloAba.isNotEmpty)
              Text(
                _tituloAba,
                style: TextStyle(
                  color: Colors.white.withValues(alpha: 0.55),
                  fontSize: 12,
                ),
              ),
          ],
        ),
        actions: [
          IconButton(
            icon: const Icon(Icons.logout, color: Color(0xFF39D0C3)),
            tooltip: 'Sair',
            onPressed: _confirmarLogout,
          ),
        ],
      ),
      body: IndexedStack(
        index: _abaAtual,
        children: _pages,
      ),
      bottomNavigationBar: NavigationBar(
        height: 74,
        backgroundColor: const Color(0xFF0B2333),
        selectedIndex: _abaAtual,
        onDestinationSelected: (i) => setState(() => _abaAtual = i),
        destinations: const [
          NavigationDestination(
            icon: Icon(Icons.home_outlined),
            selectedIcon: Icon(Icons.home),
            label: 'Inicio',
          ),
          NavigationDestination(
            icon: Icon(Icons.assignment_outlined),
            selectedIcon: Icon(Icons.assignment),
            label: 'Meu ASO',
          ),
          NavigationDestination(
            icon: Icon(Icons.school_outlined),
            selectedIcon: Icon(Icons.school),
            label: 'Treinamentos',
          ),
          NavigationDestination(
            icon: Icon(Icons.person_outline),
            selectedIcon: Icon(Icons.person),
            label: 'Perfil',
          ),
        ],
      ),
    );
  }
}
