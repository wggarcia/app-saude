import 'package:flutter/material.dart';

class TelaAlerta extends StatelessWidget {
  final String cidade;
  final String mensagem;
  final String nivel;

  const TelaAlerta({
    super.key,
    required this.cidade,
    required this.mensagem,
    required this.nivel,
  });

  Color cor() {
    if (nivel == "ALTO") return Colors.red;
    if (nivel == "MODERADO") return Colors.orange;
    if (nivel == "ATENCAO") return Colors.yellow;
    return Colors.green;
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text("Alerta de Saude")),
      body: Center(
        child: Container(
          padding: const EdgeInsets.all(20),
          margin: const EdgeInsets.all(20),
          decoration: BoxDecoration(
            color: cor().withValues(alpha: 0.2),
            borderRadius: BorderRadius.circular(10),
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text("📍 $cidade", style: const TextStyle(fontSize: 22)),
              const SizedBox(height: 10),
              Text(
                mensagem,
                style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
              ),
              const SizedBox(height: 20),

              const Text("Recomendacoes:"),

              const SizedBox(height: 10),

              const Text("• Use mascara"),
              const Text("• Evite aglomeracoes"),
              const Text("• Procure atendimento se piorar"),
            ],
          ),
        ),
      ),
    );
  }
}
