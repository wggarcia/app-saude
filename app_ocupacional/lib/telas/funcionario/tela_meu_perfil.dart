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
  Map<String, dynamic>? _perfil;
  List<dynamic> _epis = const [];
  String? _erro;
  bool _loading = true;

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
      final results = await Future.wait([
        FuncionarioSstService.perfil(),
        FuncionarioSstService.epis().catchError((_) => <String, dynamic>{}),
      ]);
      if (!mounted) return;
      final perfilData = results[0];
      final episData = results[1];
      setState(() {
        _perfil = perfilData;
        _epis = (episData['epis'] as List<dynamic>? ?? []);
      });
    } catch (e) {
      if (!mounted) return;
      setState(() => _erro = e.toString().replaceFirst('Exception: ', ''));
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _logout() async {
    await FuncionarioAuthService.logout();
    if (!mounted) return;
    Navigator.of(context).pushReplacement(
      MaterialPageRoute(builder: (_) => const TelaLoginFuncionario()),
    );
  }

  String _iniciais(String nome) {
    final partes = nome.trim().split(' ').where((p) => p.isNotEmpty).toList();
    if (partes.isEmpty) return '?';
    if (partes.length == 1) return partes[0][0].toUpperCase();
    return '${partes.first[0]}${partes.last[0]}'.toUpperCase();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Meu Perfil'),
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: _carregar,
            tooltip: 'Atualizar',
          ),
        ],
      ),
      body: _buildBody(context),
    );
  }

  Widget _buildBody(BuildContext context) {
    if (_loading) return const Center(child: CircularProgressIndicator());

    if (_erro != null) {
      return Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              const Icon(Icons.cloud_off_outlined, size: 48, color: Colors.white38),
              const SizedBox(height: 12),
              Text(_erro!, textAlign: TextAlign.center,
                style: const TextStyle(color: Colors.white60)),
              const SizedBox(height: 16),
              FilledButton.icon(
                onPressed: _carregar,
                icon: const Icon(Icons.refresh),
                label: const Text('Tentar novamente'),
              ),
            ],
          ),
        ),
      );
    }

    final p = _perfil ?? {};
    final nome = (p['nome'] ?? 'Trabalhador').toString();

    return RefreshIndicator(
      onRefresh: _carregar,
      child: ListView(
        padding: const EdgeInsets.all(16),
        children: [
          // ── Avatar + nome ──
          Center(
            child: Column(
              children: [
                Container(
                  width: 80,
                  height: 80,
                  decoration: BoxDecoration(
                    shape: BoxShape.circle,
                    gradient: const LinearGradient(
                      colors: [Color(0xFF27D3BE), Color(0xFF0B6B8A)],
                    ),
                    boxShadow: [
                      BoxShadow(
                        color: const Color(0xFF27D3BE).withValues(alpha: 0.3),
                        blurRadius: 20,
                        offset: const Offset(0, 6),
                      ),
                    ],
                  ),
                  child: Center(
                    child: Text(
                      _iniciais(nome),
                      style: const TextStyle(
                        color: Colors.white,
                        fontSize: 28,
                        fontWeight: FontWeight.w800,
                      ),
                    ),
                  ),
                ),
                const SizedBox(height: 12),
                Text(nome,
                  style: const TextStyle(
                    color: Colors.white,
                    fontSize: 20,
                    fontWeight: FontWeight.w800,
                  )),
                const SizedBox(height: 4),
                Text(
                  '${p['cargo'] ?? ''} • ${p['empresa_nome'] ?? ''}',
                  textAlign: TextAlign.center,
                  style: const TextStyle(color: Colors.white54, fontSize: 13),
                ),
              ],
            ),
          ),
          const SizedBox(height: 24),

          // ── Dados pessoais ──
          _Secao(
            titulo: 'Dados pessoais',
            icon: Icons.person_outline,
            campos: {
              'CPF': p['cpf'],
              'Nascimento': p['data_nascimento'],
              'ID': p['id']?.toString(),
            },
          ),
          const SizedBox(height: 12),

          // ── Dados profissionais ──
          _Secao(
            titulo: 'Dados profissionais',
            icon: Icons.badge_outlined,
            campos: {
              'Empresa': p['empresa_nome'],
              'Cargo': p['cargo'],
              'Setor': p['setor'],
              'Matrícula': p['matricula'],
            },
          ),
          const SizedBox(height: 12),

          // ── EPI ──
          if (_epis.isNotEmpty) ...[
            _EpiSecao(epis: _epis),
            const SizedBox(height: 12),
          ],

          // ── Logout ──
          const SizedBox(height: 8),
          FilledButton.icon(
            style: FilledButton.styleFrom(
              backgroundColor: const Color(0xFF3A1010),
              foregroundColor: const Color(0xFFFF6B6B),
              padding: const EdgeInsets.symmetric(vertical: 14),
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
            ),
            onPressed: _logout,
            icon: const Icon(Icons.logout),
            label: const Text('Sair da sessão'),
          ),
          const SizedBox(height: 24),
        ],
      ),
    );
  }
}

class _Secao extends StatelessWidget {
  const _Secao({required this.titulo, required this.icon, required this.campos});
  final String titulo;
  final IconData icon;
  final Map<String, dynamic> campos;

  @override
  Widget build(BuildContext context) {
    final camposValidos = campos.entries.where((e) {
      final v = e.value?.toString() ?? '';
      return v.isNotEmpty && v != 'null';
    }).toList();
    if (camposValidos.isEmpty) return const SizedBox.shrink();

    return Container(
      decoration: BoxDecoration(
        color: const Color(0xFF102A32),
        borderRadius: BorderRadius.circular(16),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(14, 14, 14, 0),
            child: Row(
              children: [
                Icon(icon, size: 16, color: const Color(0xFF27D3BE)),
                const SizedBox(width: 8),
                Text(titulo,
                  style: const TextStyle(
                    color: Color(0xFF27D3BE),
                    fontWeight: FontWeight.w700,
                    fontSize: 12,
                    letterSpacing: 0.8,
                  )),
              ],
            ),
          ),
          const SizedBox(height: 10),
          ...camposValidos.asMap().entries.map((entry) {
            final e = entry.value;
            final isLast = entry.key == camposValidos.length - 1;
            return Column(
              children: [
                Padding(
                  padding: const EdgeInsets.fromLTRB(14, 0, 14, 0),
                  child: Row(
                    children: [
                      SizedBox(
                        width: 88,
                        child: Text(e.key,
                          style: const TextStyle(color: Colors.white38, fontSize: 12)),
                      ),
                      Expanded(
                        child: Text(e.value.toString(),
                          style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w600, fontSize: 13)),
                      ),
                    ],
                  ),
                ),
                if (!isLast)
                  const Padding(
                    padding: EdgeInsets.symmetric(vertical: 8, horizontal: 14),
                    child: Divider(height: 1, color: Colors.white10),
                  )
                else
                  const SizedBox(height: 14),
              ],
            );
          }),
        ],
      ),
    );
  }
}

class _EpiSecao extends StatelessWidget {
  const _EpiSecao({required this.epis});
  final List<dynamic> epis;

  Color _statusColor(String s) {
    final v = s.toLowerCase();
    if (v.contains('venc') || v.contains('expirado')) return const Color(0xFFFF6B6B);
    if (v.contains('prazo') || v.contains('a vencer')) return const Color(0xFFFFB454);
    return const Color(0xFF27D3BE);
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      decoration: BoxDecoration(
        color: const Color(0xFF102A32),
        borderRadius: BorderRadius.circular(16),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Padding(
            padding: EdgeInsets.fromLTRB(14, 14, 14, 0),
            child: Row(
              children: [
                Icon(Icons.security_outlined, size: 16, color: Color(0xFF27D3BE)),
                SizedBox(width: 8),
                Text('EPI — Equipamentos de Proteção',
                  style: TextStyle(
                    color: Color(0xFF27D3BE),
                    fontWeight: FontWeight.w700,
                    fontSize: 12,
                    letterSpacing: 0.8,
                  )),
              ],
            ),
          ),
          const SizedBox(height: 12),
          ...epis.take(10).map((item) {
            final epi = item as Map<String, dynamic>;
            final nome = (epi['nome'] ?? epi['equipamento'] ?? 'EPI').toString();
            final ca = (epi['ca'] ?? epi['certificado_aprovacao'] ?? '').toString();
            final validade = (epi['data_vencimento'] ?? epi['validade'] ?? '').toString();
            final statusRaw = (epi['status'] ?? epi['status_display'] ?? 'ok').toString();
            final cor = _statusColor(statusRaw);
            return Padding(
              padding: const EdgeInsets.fromLTRB(14, 0, 14, 10),
              child: Row(
                children: [
                  Container(
                    width: 6,
                    height: 6,
                    decoration: BoxDecoration(color: cor, shape: BoxShape.circle),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(nome,
                          style: const TextStyle(color: Colors.white, fontWeight: FontWeight.w600, fontSize: 13)),
                        if (ca.isNotEmpty && ca != 'null')
                          Text('CA: $ca', style: const TextStyle(color: Colors.white38, fontSize: 11)),
                        if (validade.isNotEmpty && validade != 'null')
                          Text('Venc.: $validade',
                            style: TextStyle(color: cor.withValues(alpha: 0.85), fontSize: 11)),
                      ],
                    ),
                  ),
                ],
              ),
            );
          }),
          const SizedBox(height: 4),
        ],
      ),
    );
  }
}
