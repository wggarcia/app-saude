import 'package:flutter/material.dart';

import '../../servicos/funcionario_auth_service.dart';
import 'tela_dashboard_funcionario.dart';
import 'tela_meu_perfil.dart';
import 'tela_meus_asos.dart';
import 'tela_meus_treinamentos.dart';
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
  int i = 0;
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
      const TelaMeuPerfil(),
    ];
    return Scaffold(
      appBar: AppBar(
        title: Text(widget.nome),
        actions: [
          IconButton(
            onPressed: () async {
              final navigator = Navigator.of(context);
              await FuncionarioAuthService.logout();
              if (!mounted) return;
              navigator.pushReplacement(
                MaterialPageRoute(builder: (_) => const TelaLoginFuncionario()),
              );
            },
            icon: const Icon(Icons.logout),
          ),
        ],
      ),
      body: pages[i],
      bottomNavigationBar: NavigationBar(
        selectedIndex: i,
        onDestinationSelected: (v) => setState(() => i = v),
        destinations: const [
          NavigationDestination(
            icon: Icon(Icons.home_outlined),
            label: 'Início',
          ),
          NavigationDestination(
            icon: Icon(Icons.assignment_outlined),
            label: 'ASO',
          ),
          NavigationDestination(
            icon: Icon(Icons.school_outlined),
            label: 'Treinamentos',
          ),
          NavigationDestination(
            icon: Icon(Icons.person_outline),
            label: 'Perfil',
          ),
        ],
      ),
    );
  }
}
