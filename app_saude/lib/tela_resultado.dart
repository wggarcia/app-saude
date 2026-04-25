import 'package:flutter/material.dart';

class TelaResultado extends StatelessWidget {
  final String grupo;
  final String classificacao;

  const TelaResultado({
    super.key,
    required this.grupo,
    required this.classificacao,
  });

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text("Resultado"),
        backgroundColor: Colors.red,
      ),
      body: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [

            const Text(
              "⚠️ Avaliação inicial",
              style: TextStyle(fontSize: 22, fontWeight: FontWeight.bold),
            ),

            const SizedBox(height: 20),

            const Text(
              "🧠 Padrão identificado:",
              style: TextStyle(fontSize: 18),
            ),

            const SizedBox(height: 8),

            Text(
              grupo,
              style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold, color: Colors.red),
            ),

            const SizedBox(height: 20),

            const Text(
              "📄 Descrição:",
              style: TextStyle(fontSize: 18),
            ),

            const SizedBox(height: 8),

            Text(
              classificacao,
              style: TextStyle(fontSize: 16),
            ),

            const SizedBox(height: 30),

            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: Colors.yellow[100],
                borderRadius: BorderRadius.circular(10),
              ),
              child: const Text(
                "⚠️ Esta é uma avaliação automatizada e não substitui um diagnóstico médico.",
                style: TextStyle(fontSize: 14),
              ),
            ),

            const Spacer(),

            SizedBox(
              width: double.infinity,
              child: ElevatedButton(
                onPressed: () {
                  Navigator.pop(context);
                },
                style: ElevatedButton.styleFrom(
                  backgroundColor: Colors.red,
                ),
                child: const Text("Voltar"),
              ),
            )
          ],
        ),
      ),
    );
  }
}
