import 'package:flutter/material.dart';
import '../../servicos/api_servico.dart';
import '../home/tela_home.dart';

class TelaLogin extends StatefulWidget {
  const TelaLogin({super.key});

  @override
  State<TelaLogin> createState() => _TelaLoginState();
}

class _TelaLoginState extends State<TelaLogin> {

  final email = TextEditingController();
  final senha = TextEditingController();
  bool loading = false;

  void entrar() async {
    setState(() => loading = true);

    final ok = await ApiServico.login(email.text, senha.text);

    setState(() => loading = false);

    if (ok) {
      Navigator.pushReplacement(
        context,
        MaterialPageRoute(builder: (_) => const TelaHome()),
      );
    } else {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text("Login inválido")),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
  body: Center(
    child: Padding(
      padding: const EdgeInsets.all(24),
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          const Icon(Icons.health_and_safety, size: 80, color: Colors.blue),
          const SizedBox(height: 20),
          const Text("Saúde Inteligente", style: TextStyle(fontSize: 24, fontWeight: FontWeight.bold)),
          const SizedBox(height: 20),
          TextField(controller: email, decoration: const InputDecoration(labelText: "Email")),
          TextField(controller: senha, obscureText: true, decoration: const InputDecoration(labelText: "Senha")),
          const SizedBox(height: 20),
          ElevatedButton(
            onPressed: loading ? null : entrar,
            style: ElevatedButton.styleFrom(minimumSize: const Size(double.infinity, 50)),
            child: loading ? const CircularProgressIndicator() : const Text("Entrar"),
          )
        ],
      ),
    ),
  ),
);