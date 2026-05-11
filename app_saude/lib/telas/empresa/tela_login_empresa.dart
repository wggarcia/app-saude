import 'package:flutter/material.dart';
import '../../servicos/empresa_auth_service.dart';
import 'navegador_sst.dart';

class TelaLoginEmpresa extends StatefulWidget {
  const TelaLoginEmpresa({super.key});

  @override
  State<TelaLoginEmpresa> createState() => _TelaLoginEmpresaState();
}

class _TelaLoginEmpresaState extends State<TelaLoginEmpresa> {
  static const _bg = Color(0xFF04131F);
  static const _card = Color(0xFF0B2333);
  static const _accent = Color(0xFF39D0C3);

  final _formKey = GlobalKey<FormState>();
  final _emailCtrl = TextEditingController();
  final _senhaCtrl = TextEditingController();

  bool _loading = false;
  bool _senhaVisivel = false;
  String? _erro;

  @override
  void dispose() {
    _emailCtrl.dispose();
    _senhaCtrl.dispose();
    super.dispose();
  }

  Future<void> _entrar() async {
    if (!(_formKey.currentState?.validate() ?? false)) return;
    setState(() {
      _loading = true;
      _erro = null;
    });
    try {
      await EmpresaAuthService.login(
        _emailCtrl.text.trim(),
        _senhaCtrl.text,
      );
      if (!mounted) return;
      Navigator.of(context).pushReplacement(
        MaterialPageRoute(builder: (_) => const NavegadorSST()),
      );
    } catch (e) {
      if (!mounted) return;
      setState(() {
        _erro = e.toString().replaceFirst('Exception: ', '');
        _loading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: _bg,
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 32),
            child: Column(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                _Logo(),
                const SizedBox(height: 10),
                const Text(
                  'Gestao SST',
                  style: TextStyle(
                    color: _accent,
                    fontSize: 14,
                    fontWeight: FontWeight.w700,
                    letterSpacing: 1.2,
                  ),
                ),
                const SizedBox(height: 8),
                Text(
                  'Acesso exclusivo para gestores de empresa',
                  style: TextStyle(
                    color: Colors.white.withValues(alpha: 0.55),
                    fontSize: 13,
                  ),
                  textAlign: TextAlign.center,
                ),
                const SizedBox(height: 36),
                Container(
                  padding: const EdgeInsets.all(24),
                  decoration: BoxDecoration(
                    color: _card,
                    borderRadius: BorderRadius.circular(24),
                    border: Border.all(
                      color: _accent.withValues(alpha: 0.18),
                    ),
                  ),
                  child: Form(
                    key: _formKey,
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        const Text(
                          'Entrar na plataforma',
                          style: TextStyle(
                            color: Colors.white,
                            fontSize: 20,
                            fontWeight: FontWeight.w800,
                          ),
                        ),
                        const SizedBox(height: 20),
                        TextFormField(
                          controller: _emailCtrl,
                          keyboardType: TextInputType.emailAddress,
                          textInputAction: TextInputAction.next,
                          autocorrect: false,
                          style: const TextStyle(color: Colors.white),
                          decoration: _inputDecoration(
                            label: 'E-mail corporativo',
                            icon: Icons.email_outlined,
                          ),
                          validator: (v) {
                            if (v == null || v.trim().isEmpty) {
                              return 'Informe o e-mail.';
                            }
                            if (!v.contains('@')) {
                              return 'E-mail invalido.';
                            }
                            return null;
                          },
                        ),
                        const SizedBox(height: 16),
                        TextFormField(
                          controller: _senhaCtrl,
                          obscureText: !_senhaVisivel,
                          textInputAction: TextInputAction.done,
                          onFieldSubmitted: (_) => _entrar(),
                          style: const TextStyle(color: Colors.white),
                          decoration: _inputDecoration(
                            label: 'Senha',
                            icon: Icons.lock_outline,
                          ).copyWith(
                            suffixIcon: IconButton(
                              icon: Icon(
                                _senhaVisivel
                                    ? Icons.visibility_off_outlined
                                    : Icons.visibility_outlined,
                                color: Colors.white38,
                              ),
                              onPressed: () => setState(
                                  () => _senhaVisivel = !_senhaVisivel),
                            ),
                          ),
                          validator: (v) {
                            if (v == null || v.isEmpty) {
                              return 'Informe a senha.';
                            }
                            return null;
                          },
                        ),
                        const SizedBox(height: 10),
                        if (_erro != null) ...[
                          const SizedBox(height: 6),
                          Container(
                            padding: const EdgeInsets.symmetric(
                                horizontal: 14, vertical: 10),
                            decoration: BoxDecoration(
                              color: const Color(0xFF4A1010),
                              borderRadius: BorderRadius.circular(14),
                              border: Border.all(
                                  color: const Color(0xFFFF6B6B)
                                      .withValues(alpha: 0.5)),
                            ),
                            child: Row(
                              children: [
                                const Icon(Icons.error_outline,
                                    color: Color(0xFFFF6B6B), size: 18),
                                const SizedBox(width: 8),
                                Expanded(
                                  child: Text(
                                    _erro!,
                                    style: const TextStyle(
                                      color: Color(0xFFFF6B6B),
                                      fontSize: 13,
                                    ),
                                  ),
                                ),
                              ],
                            ),
                          ),
                          const SizedBox(height: 6),
                        ],
                        const SizedBox(height: 8),
                        SizedBox(
                          height: 52,
                          child: FilledButton(
                            onPressed: _loading ? null : _entrar,
                            style: FilledButton.styleFrom(
                              backgroundColor: _accent,
                              foregroundColor: const Color(0xFF04131F),
                              shape: RoundedRectangleBorder(
                                borderRadius: BorderRadius.circular(16),
                              ),
                            ),
                            child: _loading
                                ? const SizedBox(
                                    width: 22,
                                    height: 22,
                                    child: CircularProgressIndicator(
                                      strokeWidth: 2.5,
                                      color: Color(0xFF04131F),
                                    ),
                                  )
                                : const Text(
                                    'Entrar',
                                    style: TextStyle(
                                      fontSize: 16,
                                      fontWeight: FontWeight.w700,
                                    ),
                                  ),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
                const SizedBox(height: 32),
                TextButton(
                  onPressed: () => Navigator.of(context).pop(),
                  child: const Text(
                    'Voltar ao app publico',
                    style: TextStyle(color: Color(0xFF9CC4DB)),
                  ),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }

  InputDecoration _inputDecoration(
      {required String label, required IconData icon}) {
    return InputDecoration(
      labelText: label,
      labelStyle: const TextStyle(color: Colors.white54),
      prefixIcon: Icon(icon, color: Colors.white38),
      filled: true,
      fillColor: const Color(0xFF112D40),
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(14),
        borderSide: BorderSide.none,
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(14),
        borderSide: BorderSide(
          color: _accent.withValues(alpha: 0.18),
        ),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(14),
        borderSide: const BorderSide(color: _accent, width: 1.5),
      ),
      errorBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(14),
        borderSide: const BorderSide(color: Color(0xFFFF6B6B)),
      ),
      focusedErrorBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(14),
        borderSide: const BorderSide(color: Color(0xFFFF6B6B), width: 1.5),
      ),
      errorStyle: const TextStyle(color: Color(0xFFFF6B6B)),
    );
  }
}

class _Logo extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Container(
          width: 72,
          height: 72,
          decoration: BoxDecoration(
            color: const Color(0xFF0B2333),
            borderRadius: BorderRadius.circular(20),
            border: Border.all(
              color: const Color(0xFF39D0C3).withValues(alpha: 0.4),
              width: 1.5,
            ),
          ),
          child: const Center(
            child: Icon(
              Icons.health_and_safety_outlined,
              color: Color(0xFF39D0C3),
              size: 36,
            ),
          ),
        ),
        const SizedBox(height: 14),
        const Text(
          'SolusCRT',
          style: TextStyle(
            color: Colors.white,
            fontSize: 26,
            fontWeight: FontWeight.w900,
            letterSpacing: 0.5,
          ),
        ),
      ],
    );
  }
}
