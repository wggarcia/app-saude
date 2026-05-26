import 'dart:async';
import 'package:flutter/material.dart';

import '../../servicos/funcionario_auth_service.dart';
import '../../servicos/funcionario_sst_service.dart';
import 'tela_comunicados.dart';
import 'tela_dashboard_funcionario.dart';
import 'tela_meu_perfil.dart';
import 'tela_meus_asos.dart';
import 'tela_meus_epis.dart';
import 'tela_meus_treinamentos.dart';
import 'tela_bem_estar.dart';
import 'tela_notificacoes.dart';
import 'tela_psicossocial.dart';
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
  int _naoLidasNotif = 0;
  int _naoLidosComunicados = 0;
  Timer? _timer;

  // ── índices das abas ────────────────────────────────────────────────────
  static const _iInicio = 0;
  static const _iAso = 1;
  static const _iEpis = 2;
  static const _iTreinamentos = 3;
  static const _iComunicados = 4;
  static const _iBemEstar = 5;
  static const _iAvisos = 6;
  static const _iPerfil = 7;

  @override
  void initState() {
    super.initState();
    _pollBadges();
    _timer = Timer.periodic(const Duration(seconds: 60), (_) => _pollBadges());
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  Future<void> _pollBadges() async {
    try {
      final results = await Future.wait([
        FuncionarioSstService.notificacoes().catchError((_) => <String, dynamic>{}),
        FuncionarioSstService.comunicados().catchError((_) => <String, dynamic>{}),
      ]);
      if (!mounted) return;
      final notif = results[0];
      final com = results[1];
      setState(() {
        _naoLidasNotif = (notif['nao_lidas'] as int?) ?? 0;
        // Conta comunicados não lidos da lista
        final lista = (com['comunicados'] ?? com['mensagens'] ?? []) as List;
        _naoLidosComunicados =
            lista.where((c) => (c as Map)['lido'] == false).length;
      });
    } catch (_) {}
  }

  void _onNotificacoesLidas() => setState(() => _naoLidasNotif = 0);

  Future<void> _logout() async {
    _timer?.cancel();
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
      // 0 ─ Início
      TelaDashboardFuncionario(
        nome: widget.nome,
        cargo: widget.cargo,
        empresaNome: widget.empresaNome,
      ),
      // 1 ─ ASO
      const TelaMeusAsos(),
      // 2 ─ EPIs + Biometria
      const TelaMeusEpis(),
      // 3 ─ Treinamentos
      const TelaMeusTreinamentos(),
      // 4 ─ Comunicados SST
      const TelaComunicados(),
      // 5 ─ Bem-estar + Psicossocial
      const _BemEstarComPsico(),
      // 6 ─ Avisos / Notificações
      TelaNotificacoes(onLidas: _onNotificacoesLidas),
      // 7 ─ Perfil
      const TelaMeuPerfil(),
    ];

    return Scaffold(
      appBar: AppBar(
        title: Text(widget.nome),
        actions: [
          IconButton(
            onPressed: _pollBadges,
            icon: const Icon(Icons.refresh),
            tooltip: 'Atualizar',
          ),
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
          if (v == _iAvisos) _pollBadges();
        },
        destinations: [
          // 0 ─ Início
          const NavigationDestination(
            icon: Icon(Icons.home_outlined),
            selectedIcon: Icon(Icons.home),
            label: 'Início',
          ),
          // 1 ─ ASO
          const NavigationDestination(
            icon: Icon(Icons.assignment_outlined),
            selectedIcon: Icon(Icons.assignment),
            label: 'ASO',
          ),
          // 2 ─ EPIs
          const NavigationDestination(
            icon: Icon(Icons.security_outlined),
            selectedIcon: Icon(Icons.security),
            label: 'EPIs',
          ),
          // 3 ─ Treinamentos
          const NavigationDestination(
            icon: Icon(Icons.school_outlined),
            selectedIcon: Icon(Icons.school),
            label: 'Treinamentos',
          ),
          // 4 ─ Comunicados
          NavigationDestination(
            icon: Badge(
              isLabelVisible: _naoLidosComunicados > 0,
              label: Text('$_naoLidosComunicados'),
              child: const Icon(Icons.campaign_outlined),
            ),
            selectedIcon: Badge(
              isLabelVisible: _naoLidosComunicados > 0,
              label: Text('$_naoLidosComunicados'),
              child: const Icon(Icons.campaign),
            ),
            label: 'Comunicados',
          ),
          // 5 ─ Bem-estar
          const NavigationDestination(
            icon: Icon(Icons.favorite_outline),
            selectedIcon: Icon(Icons.favorite),
            label: 'Saúde Mental',
          ),
          // 6 ─ Avisos
          NavigationDestination(
            icon: Badge(
              isLabelVisible: _naoLidasNotif > 0,
              label: Text('$_naoLidasNotif'),
              child: const Icon(Icons.notifications_outlined),
            ),
            selectedIcon: Badge(
              isLabelVisible: _naoLidasNotif > 0,
              label: Text('$_naoLidasNotif'),
              child: const Icon(Icons.notifications),
            ),
            label: 'Avisos',
          ),
          // 7 ─ Perfil
          const NavigationDestination(
            icon: Icon(Icons.person_outline),
            selectedIcon: Icon(Icons.person),
            label: 'Perfil',
          ),
        ],
      ),
    );
  }
}

/// Tela composta: Bem-estar + acesso à avaliação Psicossocial NR-01
class _BemEstarComPsico extends StatelessWidget {
  const _BemEstarComPsico();

  static const _purple = Color(0xFF8B5CF6);
  static const _surface = Color(0xFF102A32);

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Stack(
        children: [
          // Aba padrão de Bem-estar (usa DefaultTabController)
          const TelaBemEstar(),

          // FAB flutuante para acessar Psicossocial
          Positioned(
            right: 16,
            bottom: 16,
            child: FloatingActionButton.extended(
              heroTag: 'psicossocial_fab',
              backgroundColor: _purple,
              foregroundColor: Colors.white,
              icon: const Icon(Icons.psychology_outlined),
              label: const Text('Psicossocial NR-01',
                  style: TextStyle(fontWeight: FontWeight.w800)),
              onPressed: () => Navigator.push(
                context,
                MaterialPageRoute(
                    builder: (_) => const TelaPsicossocial()),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
