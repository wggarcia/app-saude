import 'tela_sintomas.dart';
import 'package:flutter/material.dart';
import 'tela_mapa.dart';

void main() {
  runApp(AppSaude());
}

class AppSaude extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      debugShowCheckedModeBanner: false,
      title: 'Monitoramento de Saúde',
      theme: ThemeData(
        primarySwatch: Colors.red,
      ),
      home: TelaInicial(),
    );
  }
}

class TelaInicial extends StatelessWidget {
  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.white,
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(24.0),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.center,
            children: [

              SizedBox(height: 40),

              // 🧠 TÍTULO
              Text(
                "Monitoramento de Saúde",
                textAlign: TextAlign.center,
                style: TextStyle(
                  fontSize: 26,
                  fontWeight: FontWeight.bold,
                ),
              ),

              SizedBox(height: 10),

              Text(
                "Acompanhe riscos e registre sintomas em tempo real",
                textAlign: TextAlign.center,
                style: TextStyle(
                  fontSize: 16,
                  color: Colors.grey[600],
                ),
              ),

              SizedBox(height: 60),

              // 🔴 BOTÃO SINTOMAS
              SizedBox(
                width: double.infinity,
                height: 60,
                child: ElevatedButton(
                  onPressed: () {
                   Navigator.push(
                   context,
                   MaterialPageRoute(builder: (_) => TelaSintomas()),
                    );
                   },
                  style: ElevatedButton.styleFrom(
                    backgroundColor: Colors.red,
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(12),
                    ),
                  ),
                  child: Text(
                    "Estou com sintomas",
                    style: TextStyle(fontSize: 18),
                  ),
                ),
              ),

              SizedBox(height: 20),

              // 🗺️ BOTÃO MAPA
              SizedBox(
                width: double.infinity,
                height: 60,
                child: OutlinedButton(
                  onPressed: () {
                  Navigator.push(
                  context,
                  MaterialPageRoute(builder: (_) => TelaMapa()),
                    );
                  },
                  style: OutlinedButton.styleFrom(
                    side: BorderSide(color: Colors.red),
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(12),
                    ),
                  ),
                  child: Text(
                    "Ver mapa da minha região",
                    style: TextStyle(
                      fontSize: 18,
                      color: Colors.red,
                    ),
                  ),
                ),
              ),

              Spacer(),

              // ⚠️ AVISO LEGAL
              Text(
                "Este app não substitui diagnóstico médico",
                textAlign: TextAlign.center,
                style: TextStyle(
                  fontSize: 12,
                  color: Colors.grey,
                ),
              ),

              SizedBox(height: 10),
            ],
          ),
        ),
      ),
    );
  }
}

