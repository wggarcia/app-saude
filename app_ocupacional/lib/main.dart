import 'package:flutter/material.dart';

import 'telas/empresa/tela_login_empresa.dart';
import 'telas/funcionario/tela_login_funcionario.dart';

void main() {
  runApp(const SolusCrtOcupacionalApp());
}

class SolusCrtOcupacionalApp extends StatelessWidget {
  const SolusCrtOcupacionalApp({super.key});

  @override
  Widget build(BuildContext context) {
    const background = Color(0xFF071820);
    const surface = Color(0xFF102A32);
    const primary = Color(0xFF27D3BE);

    return MaterialApp(
      debugShowCheckedModeBanner: false,
      title: 'SolusCRT Ocupacional',
      theme: ThemeData(
        useMaterial3: true,
        scaffoldBackgroundColor: background,
        colorScheme: const ColorScheme.dark(
          primary: primary,
          secondary: Color(0xFFFFB454),
          surface: surface,
          error: Color(0xFFFF6B6B),
        ),
        appBarTheme: const AppBarTheme(
          backgroundColor: background,
          foregroundColor: Colors.white,
          centerTitle: false,
          elevation: 0,
        ),
        cardTheme: CardThemeData(
          color: surface,
          elevation: 0,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(16),
          ),
        ),
        inputDecorationTheme: InputDecorationTheme(
          filled: true,
          fillColor: const Color(0xFF0B2028),
          border: OutlineInputBorder(borderRadius: BorderRadius.circular(12)),
        ),
      ),
      home: const TelaEntradaOcupacional(),
      routes: {
        '/empresa': (_) => const TelaLoginEmpresa(),
        '/funcionario': (_) => const TelaLoginFuncionario(),
      },
    );
  }
}

class TelaEntradaOcupacional extends StatelessWidget {
  const TelaEntradaOcupacional({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: Center(
          child: ConstrainedBox(
            constraints: const BoxConstraints(maxWidth: 520),
            child: ListView(
              padding: const EdgeInsets.all(24),
              shrinkWrap: true,
              children: [
                const Icon(Icons.health_and_safety_outlined, size: 68),
                const SizedBox(height: 20),
                Text(
                  'SolusCRT Ocupacional',
                  textAlign: TextAlign.center,
                  style: Theme.of(context).textTheme.headlineSmall?.copyWith(
                    fontWeight: FontWeight.w800,
                  ),
                ),
                const SizedBox(height: 8),
                Text(
                  'Saúde e Segurança do Trabalho',
                  textAlign: TextAlign.center,
                  style: Theme.of(context).textTheme.bodyLarge,
                ),
                const SizedBox(height: 28),
                _AcessoButton(
                  icon: Icons.business_outlined,
                  title: 'Empresa',
                  subtitle: 'Painel SST corporativo',
                  onTap: () => Navigator.of(context).pushNamed('/empresa'),
                ),
                const SizedBox(height: 12),
                _AcessoButton(
                  icon: Icons.badge_outlined,
                  title: 'Trabalhador',
                  subtitle: 'ASO, treinamentos e perfil',
                  onTap: () => Navigator.of(context).pushNamed('/funcionario'),
                ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _AcessoButton extends StatelessWidget {
  const _AcessoButton({
    required this.icon,
    required this.title,
    required this.subtitle,
    required this.onTap,
  });

  final IconData icon;
  final String title;
  final String subtitle;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return Card(
      child: InkWell(
        borderRadius: BorderRadius.circular(16),
        onTap: onTap,
        child: Padding(
          padding: const EdgeInsets.all(18),
          child: Row(
            children: [
              Icon(
                icon,
                size: 30,
                color: Theme.of(context).colorScheme.primary,
              ),
              const SizedBox(width: 16),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      title,
                      style: Theme.of(context).textTheme.titleMedium?.copyWith(
                        fontWeight: FontWeight.w700,
                      ),
                    ),
                    const SizedBox(height: 2),
                    Text(subtitle),
                  ],
                ),
              ),
              const Icon(Icons.chevron_right),
            ],
          ),
        ),
      ),
    );
  }
}
