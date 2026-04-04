import 'package:flutter/material.dart';
import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:geolocator/geolocator.dart';

class TelaSintomas extends StatefulWidget {
  const TelaSintomas({super.key});

  @override
  State<TelaSintomas> createState() => _TelaSintomasState();
}

class _TelaSintomasState extends State<TelaSintomas> {

  bool febre = false;
  bool tosse = false;
  bool dorCorpo = false;
  bool cansaco = false;
  bool faltaAr = false;

  bool carregando = false;

  Future<Position?> obterLocalizacao() async {
  bool serviceEnabled = await Geolocator.isLocationServiceEnabled();
  if (!serviceEnabled) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text("Ative o GPS no iPhone")),
    );
    return null;
  }

  LocationPermission permission = await Geolocator.checkPermission();

  if (permission == LocationPermission.denied) {
    permission = await Geolocator.requestPermission();
  }

  if (permission == LocationPermission.denied ||
      permission == LocationPermission.deniedForever) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text("Permita acesso à localização")),
    );
    return null;
  }

  return await Geolocator.getCurrentPosition(
    desiredAccuracy: LocationAccuracy.high,
  );
}

  Future<void> enviarDados() async {
    setState(() => carregando = true);

    final pos = await obterLocalizacao();

    if (pos == null) {
  print("GPS falhou");
  ScaffoldMessenger.of(context).showSnackBar(
    const SnackBar(content: Text("Ative o GPS")),
  );
  setState(() => carregando = false);
  return;
}

// 👇 AQUI É O DEBUG
print("LAT: ${pos.latitude}");
print("LON: ${pos.longitude}");

    await http.post(
  Uri.parse("https://app-saude-p9n8.onrender.com/api/registrar-app"), // 👈 vírgula aqui
  headers: {"Content-Type": "application/json"},
  body: jsonEncode({
    "febre": febre,
    "tosse": tosse,
    "dor_corpo": dorCorpo,
    "cansaco": cansaco,
    "falta_ar": faltaAr,
    "latitude": pos.latitude,
    "longitude": pos.longitude,
  }),
);

    setState(() => carregando = false);

    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text("Dados enviados com sucesso")),
    );
  }

  Widget item(String texto, bool valor, Function(bool?) onChanged) {
    return Card(
      elevation: 2,
      child: CheckboxListTile(
        value: valor,
        onChanged: onChanged,
        title: Text(texto),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFFF5F7FB),
      appBar: AppBar(
        title: const Text("Registrar Sintomas"),
        backgroundColor: Colors.blue,
      ),
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          children: [

            item("Febre", febre, (v) => setState(() => febre = v!)),
            item("Tosse", tosse, (v) => setState(() => tosse = v!)),
            item("Dor no corpo", dorCorpo, (v) => setState(() => dorCorpo = v!)),
            item("Cansaço", cansaco, (v) => setState(() => cansaco = v!)),
            item("Falta de ar", faltaAr, (v) => setState(() => faltaAr = v!)),

            const SizedBox(height: 30),

            carregando
                ? const CircularProgressIndicator()
                : ElevatedButton(
                    onPressed: enviarDados,
                    style: ElevatedButton.styleFrom(
                      minimumSize: const Size(double.infinity, 55),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(12),
                      ),
                    ),
                    child: const Text("Enviar"),
                  ),
          ],
        ),
      ),
    );
  }
}