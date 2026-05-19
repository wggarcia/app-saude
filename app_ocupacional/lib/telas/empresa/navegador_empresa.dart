import 'package:flutter/material.dart';

import '../../servicos/empresa_auth_service.dart';
import 'tela_dashboard_empresa.dart';
import 'tela_bem_estar_empresa.dart';
import 'tela_funcionarios_empresa.dart';
import 'tela_alertas_empresa.dart';
import 'tela_login_empresa.dart';

class NavegadorEmpresa extends StatefulWidget {
  const NavegadorEmpresa({super.key, required this.empresaNome});
  final String empresaNome;

  @override
  State<NavegadorEmpresa> createState() => _NavegadorEmpresaState();
}

class _NavegadorEmpresaState extends State<NavegadorEmpresa> {
  int _idx = 0;

  Future<void> _logout() async {
    await EmpresaAuthService.logout();
    if (!mounted) return;
    Navigator.of(context).pushReplacement(
      MaterialPageRoute(builder: (_) => const TelaLoginEmpresa()),
    );
  }

  @override
  Widget build(BuildContext context) {
    final pages = [
      TelaDashboardEmpresa(empresaNome: widget.empresaNome),
      const TelaFuncionariosEmpresa(),
      const TelaBemEstarEmpresa(),
      const TelaAlertasEmpresa(),
    ];

    return Scaffold(
      appBar: AppBar(
        title: Text(widget.empresaNome),
        actions: [
          IconButton(
            icon: const Icon(Icons.logout),
            tooltip: 'Sair',
            onPressed: _logout,
          ),
        ],
      ),
      body: pages[_idx],
      bottomNavigationBar: NavigationBar(
        selectedIndex: _idx,
        onDestinationSelected: (v) => setState(() => _idx = v),
        destinations: const [
          NavigationDestination(
            icon: Icon(Icons.dashboard_outlined),
            selectedIcon: Icon(Icons.dashboard),
            label: 'Dashboard',
          ),
          NavigationDestination(
            icon: Icon(Icons.groups_outlined),
            selectedIcon: Icon(Icons.groups),
            label: 'Equipe',
          ),
          NavigationDestination(
            icon: Icon(Icons.favorite_outline),
            selectedIcon: Icon(Icons.favorite),
            label: 'Bem-estar',
          ),
          NavigationDestination(
            icon: Icon(Icons.warning_amber_outlined),
            selectedIcon: Icon(Icons.warning_amber),
            label: 'Alertas SST',
          ),
        ],
      ),
    );
  }
}
