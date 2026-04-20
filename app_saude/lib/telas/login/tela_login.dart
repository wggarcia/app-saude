import 'package:flutter/material.dart';

import '../home/tela_home.dart';

class TelaLogin extends StatelessWidget {
  const TelaLogin({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Acesso populacao')),
      body: Center(
        child: Padding(
          padding: const EdgeInsets.all(24),
          child: Column(
            mainAxisAlignment: MainAxisAlignment.center,
            children: [
              const Icon(Icons.health_and_safety, size: 82, color: Color(0xFF39D0C3)),
              const SizedBox(height: 20),
              const Text(
                'O app da populacao funciona sem login obrigatorio.',
                textAlign: TextAlign.center,
                style: TextStyle(
                  color: Colors.white,
                  fontSize: 22,
                  fontWeight: FontWeight.w700,
                ),
              ),
              const SizedBox(height: 12),
              const Text(
                'Seu envio de sintomas e anonimo e ajuda a alimentar o radar epidemiologico do SolusCRT.',
                textAlign: TextAlign.center,
                style: TextStyle(color: Color(0xFF9CC4DB), height: 1.4),
              ),
              const SizedBox(height: 24),
              FilledButton(
                onPressed: () {
                  Navigator.of(context).pushReplacement(
                    MaterialPageRoute(builder: (_) => const TelaHome()),
                  );
                },
                child: const Text('Continuar'),
              ),
            ],
          ),
        ),
      ),
    );
  }
}
