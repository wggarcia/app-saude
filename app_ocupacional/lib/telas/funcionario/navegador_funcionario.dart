import 'package:flutter/material.dart';

import '../../servicos/funcionario_auth_service.dart';
import '../../servicos/funcionario_sst_service.dart';
import 'tela_dashboard_funcionario.dart';
import 'tela_meu_perfil.dart';
import 'tela_meus_asos.dart';
import 'tela_meus_treinamentos.dart';
import 'tela_notificacoes.dart';
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
  int _idx = 0;
  int _naoLidas = 0;

  @override
  void initState() {
    super.initState();
    _carregarNotificacoes();
  }

  Future<void> _carregarNotificacoes() async {
    try {
      final d = await FuncionarioSstService.notificacoes();
      if (mounted) setState(() => _naoLidas = (d['nao_lidas'] as int?) ?? 0);
    } catch (_) {}
  }

  void _onNotificacoesLidas() => setState(() => _naoLidas = 0);

  Future<void> _logout() async {
    final navigator = Navigator.of(context);
    await FuncionarioAuthService.logout();
    if (!mounted) return;
    navigator.pushReplacement(
      MaterialPageRoute(builder: (_) => const TelaLoginFuncionario()),
    );
  }

  @override
  Widget build(BuildContext context) {
    final pages = [
      TelaDashboardFuncionario(
        nome: widget.nome,
        cargo: widget.cargo,
        empresaNome: widget.empresaNome,
      ),
      const TelaMeusAsos(),
      const TelaMeusTreinamentos(),
      TelaNotificacoes(onLidas: _onNotificacoesLidas),
      const TelaMeuPerfil(),
    ];

    return Scaffold(
      appBar: AppBar(
        title: Text(widget.nome),
        actions: [
          IconButton(
            onPressed: _logout,
            icon: const Icon(Icons.logout),
            tooltip: 'Sair',
          ),
        ],
      ),
      body: pages[_idx],
      bottomNavigationBar: NavigationBar(
        selectedIndex: _idx,
        onDestinationSelected: (v) {
          setState(() => _idx = v);
          if (v == 3) _carregarNotificacoes();
        },
        destinations: [
          const NavigationDestination(
            icon: Icon(Icons.home_outlined),
            label: 'Início',
          ),
          const NavigationDestination(
            icon: Icon(Icons.assignment_outlined),
            label: 'ASO',
          ),
          const NavigationDestination(
            icon: Icon(Icons.school_outlined),
            label: 'Treinamentos',
          ),
          NavigationDestination(
            icon: Badge(
              isLabelVisible: _naoLidas > 0,
              label: Text('$_naoLidas'),
              child: const Icon(Icons.notifications_outlined),
            ),
            label: 'Avisos',
          ),
          const NavigationDestination(
            icon: Icon(Icons.person_outline),
            label: 'Perfil',
          ),
        ],
      ),
    );
  }
}
