import 'package:flutter/material.dart';

class TelaAlerta extends StatelessWidget {

  final String cidade;
  final String mensagem;
  final String nivel;

  TelaAlerta({
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
      appBar: AppBar(title: Text("Alerta de Saúde")),
      body: Center(
        child: Container(
          padding: EdgeInsets.all(20),
          margin: EdgeInsets.all(20),
          decoration: BoxDecoration(
            color: cor().withOpacity(0.2),
            borderRadius: BorderRadius.circular(10),
          ),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text("📍 $cidade", style: TextStyle(fontSize: 22)),
              SizedBox(height: 10),
              Text(
                mensagem,
                style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
              ),
              SizedBox(height: 20),

              Text("Recomendações:"),

              SizedBox(height: 10),

              Text("• Use máscara"),
              Text("• Evite aglomerações"),
              Text("• Procure atendimento se piorar"),
            ],
          ),
        ),
      ),
    );
  }
}