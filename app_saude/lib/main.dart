import 'package:flutter/material.dart';

import 'servicos/push_service.dart';
import 'telas/home/tela_home.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  await PushService.initialize();
  runApp(const SolusCrtAppSaude());
}

class SolusCrtAppSaude extends StatelessWidget {
  const SolusCrtAppSaude({super.key});

  @override
  Widget build(BuildContext context) {
    const background = Color(0xFF04131F);
    const panel = Color(0xFF0B2333);
    const accent = Color(0xFF39D0C3);

    return MaterialApp(
      debugShowCheckedModeBanner: false,
      title: 'SolusCRT Saude',
      theme: ThemeData(
        useMaterial3: true,
        scaffoldBackgroundColor: background,
        colorScheme: const ColorScheme.dark(
          primary: accent,
          secondary: Color(0xFFFFA657),
          surface: panel,
          error: Color(0xFFFF6B6B),
        ),
        appBarTheme: const AppBarTheme(
          backgroundColor: background,
          foregroundColor: Colors.white,
          elevation: 0,
          centerTitle: false,
        ),
        cardTheme: CardThemeData(
          color: panel,
          elevation: 0,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(24),
          ),
        ),
      ),
      home: const TelaHome(),
    );
  }
}
