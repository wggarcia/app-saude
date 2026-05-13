import 'package:flutter/material.dart';

void main() {
  runApp(const SolusCrtOcupacionalFallback());
}

class SolusCrtOcupacionalFallback extends StatelessWidget {
  const SolusCrtOcupacionalFallback({super.key});

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      title: 'SolusCRT Ocupacional',
      theme: ThemeData(
        useMaterial3: true,
        colorSchemeSeed: const Color(0xFF27D3BE),
      ),
      home: const _FallbackHome(),
    );
  }
}

class _FallbackHome extends StatelessWidget {
  const _FallbackHome();

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('SolusCRT Ocupacional')),
      body: const Center(
        child: Padding(
          padding: EdgeInsets.all(24),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(Icons.health_and_safety_outlined, size: 72),
              SizedBox(height: 20),
              Text(
                'SolusCRT Ocupacional',
                textAlign: TextAlign.center,
                style: TextStyle(fontSize: 28, fontWeight: FontWeight.w800),
              ),
              SizedBox(height: 8),
              Text(
                'Projeto ativo em app-saude/app_ocupacional',
                textAlign: TextAlign.center,
              ),
            ],
          ),
        ),
      ),
    );
  }
}
