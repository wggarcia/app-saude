import 'package:flutter/material.dart';
import '../sintomas/tela_sintomas.dart';
import '../mapa/tela_mapa.dart';

class TelaHome extends StatefulWidget {
  const TelaHome({super.key});

  @override
  State<TelaHome> createState() => _TelaHomeState();
}

class _TelaHomeState extends State<TelaHome> {
  int index = 0;

  final telas = [
    const TelaDashboard(),
    const TelaSintomas(),
    const TelaMapa(),
  ];

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: telas[index],
      bottomNavigationBar: BottomNavigationBar(
        currentIndex: index,
        onTap: (i) => setState(() => index = i),
        selectedItemColor: Colors.blue,
        items: const [
          BottomNavigationBarItem(icon: Icon(Icons.home), label: "Início"),
          BottomNavigationBarItem(icon: Icon(Icons.health_and_safety), label: "Sintomas"),
          BottomNavigationBarItem(icon: Icon(Icons.map), label: "Mapa"),
        ],
      ),
    );
  }
}

class TelaDashboard extends StatelessWidget {
  const TelaDashboard({super.key});

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text("Saúde Inteligente")),
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          children: [
            _card("Enviar Sintomas", Icons.monitor_heart, Colors.blue, () {
              Navigator.push(context, MaterialPageRoute(builder: (_) => const TelaSintomas()));
            }),
            _card("Mapa de Casos", Icons.map, Colors.green, () {
              Navigator.push(context, MaterialPageRoute(builder: (_) => const TelaMapa()));
            }),
          ],
        ),
      ),
    );
  }

  Widget _card(String titulo, IconData icone, Color cor, VoidCallback onTap) {
    return GestureDetector(
      onTap: onTap,
      child: Container(
        margin: const EdgeInsets.only(bottom: 16),
        padding: const EdgeInsets.all(20),
        decoration: BoxDecoration(
          color: cor,
          borderRadius: BorderRadius.circular(16),
        ),
        child: Row(
          children: [
            Icon(icone, color: Colors.white, size: 32),
            const SizedBox(width: 20),
            Text(
              titulo,
              style: const TextStyle(color: Colors.white, fontSize: 18),
            )
          ],
        ),
      ),
    );
  }
}