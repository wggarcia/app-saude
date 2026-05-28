import 'dart:async';
import 'package:flutter/material.dart';

import '../../servicos/funcionario_auth_service.dart';
import '../../servicos/funcionario_sst_service.dart';
import 'tela_chat_funcionario.dart';
import 'tela_comunicados.dart';
import 'tela_dashboard_funcionario.dart';
import 'tela_meu_perfil.dart';
import 'tela_meus_afastamentos.dart';
import 'tela_meus_asos.dart';
import 'tela_meus_epis.dart';
import 'tela_meus_treinamentos.dart';
import 'tela_minhas_solicitacoes.dart';
import 'tela_bem_estar.dart';
import 'tela_notificacoes.dart';
import 'tela_psicossocial.dart';
import 'tela_reunioes.dart';
import 'tela_login_funcionario.dart';

// ─────────────────────────────────────────────────────────────────────────────
// NavegadorFuncionario — 5 abas principais (padrão mobile)
//
//  0 · Início      — Dashboard com KPIs e alertas
//  1 · Minha SST   — ASO · Solicitações · EPIs · Treinamentos (sub-tabs)
//  2 · Comunicados — Comunicados SST · Reuniões (sub-tabs)
//  3 · Saúde       — Bem-estar + Psicossocial NR-01
//  4 · Perfil      — Meu Perfil + Notificações
// ─────────────────────────────────────────────────────────────────────────────

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

  // índice da aba Perfil — usado para acionar _pollBadges ao navegar para ela
  static const _iPerfil = 4;

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
      final com   = results[1];
      setState(() {
        _naoLidasNotif = (notif['nao_lidas'] as int?) ?? 0;
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
      // 1 ─ Minha SST (ASO · Solicitações · EPIs · Treinamentos)
      const _MinhaSST(),
      // 2 ─ Comunicados (Comunicados · Reuniões)
      const _ComunicadosEReuniones(),
      // 3 ─ Saúde (Bem-estar + FAB Psicossocial)
      const _BemEstarComPsico(),
      // 4 ─ Perfil + Notificações
      _PerfilComAvisos(
        naoLidas: _naoLidasNotif,
        onLidas: _onNotificacoesLidas,
      ),
    ];

    return Scaffold(
      appBar: AppBar(
        title: Row(
          children: [
            Container(
              width: 26,
              height: 26,
              decoration: BoxDecoration(
                color: Theme.of(context).colorScheme.primary.withAlpha(30),
                borderRadius: BorderRadius.circular(6),
              ),
              child: Icon(
                Icons.health_and_safety_outlined,
                size: 16,
                color: Theme.of(context).colorScheme.primary,
              ),
            ),
            const SizedBox(width: 8),
            Expanded(
              child: Text(
                widget.nome,
                overflow: TextOverflow.ellipsis,
                style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w600),
              ),
            ),
          ],
        ),
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
          if (v == _iPerfil) _pollBadges();
        },
        destinations: [
          // 0 ─ Início
          const NavigationDestination(
            icon:         Icon(Icons.home_outlined),
            selectedIcon: Icon(Icons.home),
            label: 'Início',
          ),
          // 1 ─ Minha SST
          const NavigationDestination(
            icon:         Icon(Icons.medical_information_outlined),
            selectedIcon: Icon(Icons.medical_information),
            label: 'Minha SST',
          ),
          // 2 ─ Comunicados
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
          // 3 ─ Saúde
          const NavigationDestination(
            icon:         Icon(Icons.favorite_outline),
            selectedIcon: Icon(Icons.favorite),
            label: 'Saúde',
          ),
          // 4 ─ Perfil
          NavigationDestination(
            icon: Badge(
              isLabelVisible: _naoLidasNotif > 0,
              label: Text('$_naoLidasNotif'),
              child: const Icon(Icons.person_outline),
            ),
            selectedIcon: Badge(
              isLabelVisible: _naoLidasNotif > 0,
              label: Text('$_naoLidasNotif'),
              child: const Icon(Icons.person),
            ),
            label: 'Perfil',
          ),
        ],
      ),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Aba 1 — Minha SST:  ASO · Exames · EPIs · Treinamentos · Afastamentos
// ─────────────────────────────────────────────────────────────────────────────
class _MinhaSST extends StatelessWidget {
  const _MinhaSST();

  @override
  Widget build(BuildContext context) {
    return DefaultTabController(
      length: 5,
      child: Scaffold(
        appBar: PreferredSize(
          preferredSize: const Size.fromHeight(kToolbarHeight - 8),
          child: Material(
            color: Theme.of(context).scaffoldBackgroundColor,
            child: const TabBar(
              isScrollable: true,
              tabAlignment: TabAlignment.start,
              labelStyle: TextStyle(fontSize: 12, fontWeight: FontWeight.w700),
              unselectedLabelStyle: TextStyle(fontSize: 12),
              tabs: [
                Tab(icon: Icon(Icons.assignment_outlined,    size: 18), text: 'ASO'),
                Tab(icon: Icon(Icons.science_outlined,       size: 18), text: 'Exames'),
                Tab(icon: Icon(Icons.security_outlined,      size: 18), text: 'EPIs'),
                Tab(icon: Icon(Icons.school_outlined,        size: 18), text: 'Treinamentos'),
                Tab(icon: Icon(Icons.work_off_outlined,      size: 18), text: 'Afastamentos'),
              ],
            ),
          ),
        ),
        body: const TabBarView(
          children: [
            TelaMeusAsos(),
            TelaMinhasSolicitacoes(),
            TelaMeusEpis(),
            TelaMeusTreinamentos(),
            TelaMeusAfastamentos(),
          ],
        ),
      ),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Aba 2 — Comunicados + Reuniões
// ─────────────────────────────────────────────────────────────────────────────
class _ComunicadosEReuniones extends StatelessWidget {
  const _ComunicadosEReuniones();

  @override
  Widget build(BuildContext context) {
    return DefaultTabController(
      length: 3,
      child: Scaffold(
        appBar: PreferredSize(
          preferredSize: const Size.fromHeight(kToolbarHeight - 8),
          child: Material(
            color: Theme.of(context).scaffoldBackgroundColor,
            child: const TabBar(
              tabs: [
                Tab(icon: Icon(Icons.campaign_outlined,   size: 18), text: 'Comunicados'),
                Tab(icon: Icon(Icons.videocam_outlined,   size: 18), text: 'Reuniões'),
                Tab(icon: Icon(Icons.chat_bubble_outline, size: 18), text: 'Chat RH'),
              ],
            ),
          ),
        ),
        body: const TabBarView(
          children: [
            TelaComunicados(),
            TelaReunioesFunc(),
            TelaChatFuncionario(),
          ],
        ),
      ),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Aba 3 — Saúde: Bem-estar + FAB Psicossocial NR-01
// ─────────────────────────────────────────────────────────────────────────────
class _BemEstarComPsico extends StatelessWidget {
  const _BemEstarComPsico();

  static const _purple = Color(0xFF8B5CF6);

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: Stack(
        children: [
          const TelaBemEstar(),
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
                MaterialPageRoute(builder: (_) => const TelaPsicossocial()),
              ),
            ),
          ),
        ],
      ),
    );
  }
}

// ─────────────────────────────────────────────────────────────────────────────
// Aba 4 — Perfil + Notificações (seção expansível)
// ─────────────────────────────────────────────────────────────────────────────
class _PerfilComAvisos extends StatefulWidget {
  const _PerfilComAvisos({required this.naoLidas, required this.onLidas});
  final int naoLidas;
  final VoidCallback onLidas;

  @override
  State<_PerfilComAvisos> createState() => _PerfilComAvisosState();
}

class _PerfilComAvisosState extends State<_PerfilComAvisos>
    with SingleTickerProviderStateMixin {
  late final TabController _tc = TabController(length: 2, vsync: this);

  @override
  void dispose() {
    _tc.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: PreferredSize(
        preferredSize: const Size.fromHeight(kToolbarHeight - 8),
        child: Material(
          color: Theme.of(context).scaffoldBackgroundColor,
          child: TabBar(
            controller: _tc,
            tabs: [
              const Tab(icon: Icon(Icons.person_outline, size: 18), text: 'Perfil'),
              Tab(
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Badge(
                      isLabelVisible: widget.naoLidas > 0,
                      label: Text('${widget.naoLidas}'),
                      child: const Icon(Icons.notifications_outlined, size: 18),
                    ),
                    const SizedBox(width: 6),
                    const Text('Avisos', style: TextStyle(fontSize: 12)),
                  ],
                ),
              ),
            ],
          ),
        ),
      ),
      body: TabBarView(
        controller: _tc,
        children: [
          const TelaMeuPerfil(),
          TelaNotificacoes(onLidas: widget.onLidas),
        ],
      ),
    );
  }
}
