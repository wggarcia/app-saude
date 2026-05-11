import 'package:flutter/material.dart';
import 'tela_dashboard_sst.dart';
import 'tela_funcionarios_sst.dart';
import 'tela_asos_sst.dart';
import 'tela_esocial_sst.dart';

class NavegadorSST extends StatefulWidget {
  const NavegadorSST({super.key});

  @override
  State<NavegadorSST> createState() => _NavegadorSSTState();
}

class _NavegadorSSTState extends State<NavegadorSST> {
  int _abaAtual = 0;

  static const _pages = [
    TelaDashboardSST(),
    TelaFuncionariosSST(),
    TelaAsosSST(),
    TelaEsocialSST(),
  ];

  @override
  Widget build(BuildContext context) {
    return Scaffold(
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
            icon: Icon(Icons.dashboard_outlined),
            selectedIcon: Icon(Icons.dashboard),
            label: 'Dashboard',
          ),
          NavigationDestination(
            icon: Icon(Icons.people_outline),
            selectedIcon: Icon(Icons.people),
            label: 'Funcionarios',
          ),
          NavigationDestination(
            icon: Icon(Icons.assignment_outlined),
            selectedIcon: Icon(Icons.assignment),
            label: 'ASO/CAT',
          ),
          NavigationDestination(
            icon: Icon(Icons.bolt_outlined),
            selectedIcon: Icon(Icons.bolt),
            label: 'eSocial',
          ),
        ],
      ),
    );
  }
}
