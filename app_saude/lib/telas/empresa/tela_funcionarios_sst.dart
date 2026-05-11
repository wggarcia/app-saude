import 'package:flutter/material.dart';
import '../../servicos/empresa_auth_service.dart';
import '../../servicos/sst_service.dart';
import 'tela_login_empresa.dart';

class TelaFuncionariosSST extends StatefulWidget {
  const TelaFuncionariosSST({super.key});

  @override
  State<TelaFuncionariosSST> createState() =>
      _TelaFuncionariosSSTState();
}

class _TelaFuncionariosSSTState extends State<TelaFuncionariosSST> {
  static const _bg = Color(0xFF04131F);
  static const _accent = Color(0xFF39D0C3);

  final _searchCtrl = TextEditingController();

  List<dynamic> _funcionarios = [];
  bool _loading = true;
  bool _carregandoMais = false;
  bool _temMais = true;
  String? _erro;
  int _pagina = 1;
  String _busca = '';

  @override
  void initState() {
    super.initState();
    _load(reiniciar: true);
  }

  @override
  void dispose() {
    _searchCtrl.dispose();
    super.dispose();
  }

  Future<void> _load({bool reiniciar = false}) async {
    if (reiniciar) {
      setState(() {
        _loading = true;
        _erro = null;
        _pagina = 1;
        _funcionarios = [];
        _temMais = true;
      });
    }
    try {
      final data = await SSTService.getFuncionarios(
        page: _pagina,
        search: _busca,
      );
      if (!mounted) return;
      List<dynamic> lista = [];
      bool temMais = false;
      if (data is List) {
        lista = data;
        temMais = data.length >= 20;
      } else if (data is Map) {
        lista = (data['results'] ?? data['funcionarios'] ?? []) as List;
        final nextPage = data['next'];
        temMais = nextPage != null;
      }
      setState(() {
        if (reiniciar) {
          _funcionarios = lista;
        } else {
          _funcionarios = [..._funcionarios, ...lista];
        }
        _temMais = temMais;
        _loading = false;
        _carregandoMais = false;
      });
    } catch (e) {
      if (!mounted) return;
      final msg = e.toString().replaceFirst('Exception: ', '');
      if (msg.contains('expirada') || msg.contains('autenticado')) {
        await EmpresaAuthService.logout();
        if (!mounted) return;
        Navigator.of(context).pushAndRemoveUntil(
          MaterialPageRoute(
              builder: (_) => const TelaLoginEmpresa()),
          (_) => false,
        );
        return;
      }
      setState(() {
        _erro = msg;
        _loading = false;
        _carregandoMais = false;
      });
    }
  }

  Future<void> _carregarMais() async {
    if (_carregandoMais || !_temMais) return;
    setState(() {
      _carregandoMais = true;
      _pagina++;
    });
    await _load();
  }

  void _onBusca(String valor) {
    setState(() => _busca = valor);
    _load(reiniciar: true);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: _bg,
      body: RefreshIndicator(
        color: _accent,
        backgroundColor: const Color(0xFF0B2333),
        onRefresh: () => _load(reiniciar: true),
        child: CustomScrollView(
          physics: const AlwaysScrollableScrollPhysics(),
          slivers: [
            const SliverAppBar(
              pinned: true,
              backgroundColor: _bg,
              foregroundColor: Colors.white,
              title: Text(
                'Funcionarios',
                style: TextStyle(
                    fontSize: 18, fontWeight: FontWeight.w800),
              ),
            ),
            SliverToBoxAdapter(
              child: Padding(
                padding: const EdgeInsets.fromLTRB(16, 8, 16, 4),
                child: SearchBar(
                  controller: _searchCtrl,
                  hintText: 'Buscar por nome...',
                  hintStyle: WidgetStateProperty.all(
                    const TextStyle(color: Colors.white38),
                  ),
                  textStyle: WidgetStateProperty.all(
                    const TextStyle(color: Colors.white),
                  ),
                  backgroundColor: WidgetStateProperty.all(
                    const Color(0xFF0B2333),
                  ),
                  shadowColor:
                      WidgetStateProperty.all(Colors.transparent),
                  leading: const Icon(Icons.search,
                      color: Colors.white38),
                  trailing: [
                    if (_searchCtrl.text.isNotEmpty)
                      IconButton(
                        icon: const Icon(Icons.clear,
                            color: Colors.white38),
                        onPressed: () {
                          _searchCtrl.clear();
                          _onBusca('');
                        },
                      ),
                  ],
                  onChanged: _onBusca,
                  onSubmitted: _onBusca,
                ),
              ),
            ),
            if (_loading)
              const SliverFillRemaining(
                child: Center(
                  child: CircularProgressIndicator(color: _accent),
                ),
              )
            else if (_erro != null)
              SliverFillRemaining(
                child: Center(
                  child: Padding(
                    padding: const EdgeInsets.all(24),
                    child: Column(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        const Icon(Icons.wifi_off_outlined,
                            color: Colors.white38, size: 48),
                        const SizedBox(height: 16),
                        Text(_erro!,
                            textAlign: TextAlign.center,
                            style: const TextStyle(
                                color: Color(0xFF9CC4DB))),
                        const SizedBox(height: 20),
                        FilledButton.icon(
                          onPressed: () => _load(reiniciar: true),
                          icon: const Icon(Icons.refresh),
                          label: const Text('Tentar novamente'),
                        ),
                      ],
                    ),
                  ),
                ),
              )
            else if (_funcionarios.isEmpty)
              const SliverFillRemaining(
                child: Center(
                  child: Text(
                    'Nenhum funcionario encontrado.',
                    style: TextStyle(color: Color(0xFF9CC4DB)),
                  ),
                ),
              )
            else
              SliverPadding(
                padding: const EdgeInsets.fromLTRB(16, 8, 16, 8),
                sliver: SliverList(
                  delegate: SliverChildBuilderDelegate(
                    (ctx, i) {
                      if (i == _funcionarios.length) {
                        return _temMais
                            ? Padding(
                                padding:
                                    const EdgeInsets.symmetric(
                                        vertical: 12),
                                child: Center(
                                  child: _carregandoMais
                                      ? const CircularProgressIndicator(
                                          color: _accent)
                                      : OutlinedButton.icon(
                                          onPressed: _carregarMais,
                                          icon: const Icon(
                                              Icons.expand_more),
                                          label: const Text(
                                              'Carregar mais'),
                                        ),
                                ),
                              )
                            : const Padding(
                                padding: EdgeInsets.symmetric(
                                    vertical: 16),
                                child: Center(
                                  child: Text(
                                    'Todos os funcionarios carregados.',
                                    style: TextStyle(
                                        color: Colors.white38,
                                        fontSize: 12),
                                  ),
                                ),
                              );
                      }
                      final f = _funcionarios[i]
                          as Map<String, dynamic>;
                      return _FuncionarioCard(funcionario: f);
                    },
                    childCount: _funcionarios.length + 1,
                  ),
                ),
              ),
          ],
        ),
      ),
    );
  }
}

class _FuncionarioCard extends StatelessWidget {
  const _FuncionarioCard({required this.funcionario});

  final Map<String, dynamic> funcionario;

  static Color _classeColor(String classe) {
    switch (classe.toLowerCase()) {
      case 'critico':
      case 'alto':
        return const Color(0xFFFF6B6B);
      case 'medio':
        return const Color(0xFFFFD166);
      default:
        return const Color(0xFF4CAF50);
    }
  }

  static String _classeLabel(String classe) {
    switch (classe.toLowerCase()) {
      case 'critico':
        return 'Critico';
      case 'alto':
        return 'Alto';
      case 'medio':
        return 'Medio';
      default:
        return 'Baixo';
    }
  }

  @override
  Widget build(BuildContext context) {
    final nome = funcionario['nome']?.toString() ?? 'Sem nome';
    final cargo = funcionario['cargo']?.toString() ?? '--';
    final unidade =
        funcionario['unidade']?.toString() ?? '--';
    final admissao =
        funcionario['data_admissao']?.toString() ?? '--';
    final classeRaw =
        funcionario['classe_risco']?.toString() ?? 'baixo';
    final classeColor = _classeColor(classeRaw);
    final classeLabel = _classeLabel(classeRaw);

    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: const Color(0xFF0B2333),
        borderRadius: BorderRadius.circular(18),
        border: Border.all(
          color: const Color(0xFF39D0C3).withValues(alpha: 0.12),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  nome,
                  style: const TextStyle(
                    color: Colors.white,
                    fontWeight: FontWeight.w700,
                    fontSize: 15,
                  ),
                ),
              ),
              Container(
                padding: const EdgeInsets.symmetric(
                    horizontal: 10, vertical: 4),
                decoration: BoxDecoration(
                  color: classeColor.withValues(alpha: 0.15),
                  borderRadius: BorderRadius.circular(10),
                  border: Border.all(
                      color: classeColor.withValues(alpha: 0.5)),
                ),
                child: Text(
                  classeLabel,
                  style: TextStyle(
                    color: classeColor,
                    fontSize: 11,
                    fontWeight: FontWeight.w700,
                  ),
                ),
              ),
            ],
          ),
          const SizedBox(height: 8),
          Wrap(
            spacing: 12,
            runSpacing: 6,
            children: [
              _InfoChip(icon: Icons.work_outline, label: cargo),
              _InfoChip(
                  icon: Icons.business_outlined,
                  label: unidade),
              _InfoChip(
                  icon: Icons.calendar_today_outlined,
                  label: 'Adm: $admissao'),
            ],
          ),
        ],
      ),
    );
  }
}

class _InfoChip extends StatelessWidget {
  const _InfoChip({required this.icon, required this.label});

  final IconData icon;
  final String label;

  @override
  Widget build(BuildContext context) {
    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Icon(icon, size: 13, color: const Color(0xFF9CC4DB)),
        const SizedBox(width: 4),
        Text(
          label,
          style: const TextStyle(
            color: Color(0xFF9CC4DB),
            fontSize: 12,
          ),
        ),
      ],
    );
  }
}
