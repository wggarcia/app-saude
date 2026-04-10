import 'package:flutter/material.dart';
import 'dart:convert';
import 'package:http/http.dart' as http;
import 'package:geocoding/geocoding.dart';

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

  Future<void> enviarDados() async {
    setState(() => carregando = true);

    final pos = await obterLocalizacao();

    if (pos == null) {
      setState(() => carregando = false);
      return;
    }

    double lat = pos["lat"]!;
    double lon = pos["lon"]!;

    print("LAT: $lat");
    print("LON: $lon");

    try {
      List<Placemark> placemarks =
          await placemarkFromCoordinates(lat, lon);

      String cidade = placemarks.first.locality ?? "Desconhecido";

      final response = await http.post(
        Uri.parse("https://app-saude-p9n8.onrender.com/api/registrar-app"),
        headers: {"Content-Type": "application/json"},
        body: jsonEncode({
          "febre": febre,
          "tosse": tosse,
          "dor_corpo": dorCorpo,
          "cansaco": cansaco,
          "falta_ar": faltaAr,
          "latitude": lat,
          "longitude": lon,
          "cidade": cidade,
        }),
      );

      print("STATUS ENVIO: ${response.statusCode}");
      print("BODY ENVIO: ${response.body}");

      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text("Enviado com sucesso")),
      );

      Navigator.pop(context);
    } catch (e) {
      print("ERRO ENVIO: $e");

      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text("Erro ao enviar")),
      );

      Navigator.pop(context);
    }

    setState(() => carregando = false);
  }

  Widget item(String texto, bool valor, Function(bool?) onChanged) {
    return Card(
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
      appBar: AppBar(title: const Text("Registrar Sintomas")),
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
                    child: const Text("Enviar"),
                  ),
          ],
        ),
      ),
    );
  }
}

// 🔥 LOCALIZAÇÃO VIA IP (funcionando)
Future<Map<String, double>?> obterLocalizacao() async {
  try {
    final response = await http.get(
      Uri.parse("https://ipapi.co/json/"),
    );

    if (response.statusCode == 200) {
      final data = jsonDecode(response.body);

      return {
        "lat": (data["latitude"] as num).toDouble(),
        "lon": (data["longitude"] as num).toDouble(),
      };
    }
  } catch (e) {
    print("Erro localização: $e");
  }

  return null;
}